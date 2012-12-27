# -*- coding: utf-8 -*-
##############################################################################
#
#    hr_holidays_timebank module for OpenERP, Let to tranfer allocation to an other allocation
#    Copyright (C) 2012 SYLEAM Info Services (<http://www.syleam.fr/>)
#              Sebastien LANGE <sebastien.lange@syleam.fr>
#
#    This file is a part of hr_holidays_timebank
#
#    hr_holidays_timebank is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    hr_holidays_timebank is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from osv import osv
from osv import fields
import netsvc
from tools.translate import _


class hr_holidays(osv.osv):
    _inherit = 'hr.holidays'

    _columns = {
        'timebank': fields.boolean('Timebank', help='Transfer Leave'),
    }

    _defaults = {
        'timebank': False,
    }

hr_holidays()


class hr_holidays_timebank(osv.osv):
    _name = 'hr.holidays.timebank'
    _description = 'HR Holidays Timebank'
    _table = "hr_holidays_timebank"
    _inherits = {'hr.holidays': 'hr_holidays_id'}

    _columns = {
        'holiday_status_to_id': fields.many2one('hr.holidays.status', 'Leave Type (To)', required=True, readonly=True, states={'draft': [('readonly', False)]}),
        'hr_holidays_id': fields.many2one('hr.holidays', 'Holidays (From)', required=True, ondelete='cascade'),
        'hr_holidays_to_id': fields.many2one('hr.holidays', 'Holidays (To)', ondelete='cascade'),
    }

    _defaults = {
        'timebank': True,
    }

    def onchange_sec_id(self, cr, uid, ids, status, context=None):
        warning = {}
        double_validation = False
        obj_holiday_status = self.pool.get('hr.holidays.status')
        if status:
            holiday_status = obj_holiday_status.browse(cr, uid, status, context=context)
            double_validation = holiday_status.double_validation
            if holiday_status.categ_id and holiday_status.categ_id.section_id and not holiday_status.categ_id.section_id.allow_unlink:
                warning = {
                    'title': "Warning for ",
                    'message': "You won\'t be able to cancel this leave request because the CRM Sales Team of the leave type disallows."
                }
        return {'warning': warning, 'value': {'double_validation': double_validation}}

    def _get_employee(self, cr, uid, ids, context=None):
        """
        Get employee
        """
        ids2 = self.pool.get('hr.employee').search(cr, uid, [('user_id', '=', uid)], context=context)
        return ids2 and ids2[0] or False

    def holidays_confirm(self, cr, uid, ids, context=None):
        self.check_holidays(cr, uid, ids, context=context)
        return self.write(cr, uid, ids, {'state': 'confirm'}, context=context)

    def holidays_validate(self, cr, uid, ids, context=None):
        self.check_holidays(cr, uid, ids, context=context)
        return self.write(cr, uid, ids, {'state': 'validate1', 'manager_id': self._get_employee(cr, uid, ids, context=context)}, context=context)

    def holidays_validate2(self, cr, uid, ids, context=None):
        holiday_obj = self.pool.get('hr.holidays')
        self.check_holidays(cr, uid, ids, context=context)
        self.write(cr, uid, ids, {'state': 'validate'}, context=context)
        holiday_ids = []
        for record in self.browse(cr, uid, ids, context=context):
            if record.holiday_status_id.double_validation:
                holiday_ids.append(record.id)
            # Create new allocation
            if not record.hr_holidays_to_id:
                holiday_id = holiday_obj.copy(cr, uid, record.hr_holidays_id.id, {
                    'holiday_status_id': record.holiday_status_to_id.id,
                    'type': 'add',
                }, context=context)
                self.write(cr, uid, [record.id], {'hr_holidays_to_id': holiday_id}, context=context)
            else:
                holiday_id = record.hr_holidays_to_id.id
            wf_service = netsvc.LocalService("workflow")
            wf_service.trg_validate(uid, 'hr.holidays', holiday_id, 'confirm', cr)
            wf_service.trg_validate(uid, 'hr.holidays', holiday_id, 'validate', cr)
            wf_service.trg_validate(uid, 'hr.holidays', holiday_id, 'second_validate', cr)

        if holiday_ids:
            self.write(cr, uid, holiday_ids, {'manager_id2': self._get_employee(cr, uid, ids, context=context)})
        return True

    def check_holidays(self, cr, uid, ids, context=None):
        holiday_ids = [timebank.hr_holidays_id.id for timebank in self.browse(cr, uid, ids, context=context)]
        return self.pool.get('hr.holidays').check_holidays(cr, uid, holiday_ids, context=context)

    def set_to_draft(self, cr, uid, ids, context=None):
        vals = {
            'state': 'draft',
            'manager_id': False,
            'manager_id2': False,
        }
        holiday_obj = self.pool.get('hr.holidays')
        self.write(cr, uid, ids, vals, context=context)
        wf_service = netsvc.LocalService("workflow")
        for timebank in self.browse(cr, uid, ids, context=context):
            wf_service.trg_delete(uid, 'hr.holidays.timebank', timebank.id, cr)
            wf_service.trg_create(uid, 'hr.holidays.timebank', timebank.id, cr)
            if timebank.hr_holidays_to_id:
                holiday_obj.write(cr, uid, [timebank.hr_holidays_to_id.id], vals, context=context)
                wf_service.trg_delete(uid, 'hr.holidays', timebank.hr_holidays_to_id.id, cr)
                wf_service.trg_create(uid, 'hr.holidays', timebank.hr_holidays_to_id.id, cr)
        return True

    def holidays_refuse(self, cr, uid, ids, approval, context=None):
        manager = self._get_employee(cr, uid, ids, context=context)
        if approval == 'first_approval':
            self.write(cr, uid, ids, {'state': 'refuse', 'manager_id': manager}, context=context)
        else:
            self.write(cr, uid, ids, {'state': 'refuse', 'manager_id2': manager}, context=context)
        self.holidays_cancel(cr, uid, ids, context=context)
        return True

    def holidays_cancel(self, cr, uid, ids, context=None):
        for record in self.browse(cr, uid, ids, context=context):
            wf_service = netsvc.LocalService("workflow")
            wf_service.trg_validate(uid, 'hr.holidays', record.hr_holidays_to_id.id, 'cancel', cr)
        return True

    def copy(self, cr, uid, id, default=None, context=None):
        """
        Remove hr holiday link
        """
        default = {
            'state': 'draft',
            'hr_holidays_to_id': False,
            'hr_holidays_id': False,
            'manager_id': False,
            'manager_id2': False,
        }
        return super(hr_holidays_timebank, self).copy(cr, uid, id, default, context=context)

    def unlink(self, cr, uid, ids, context=None):
        for rec in self.browse(cr, uid, ids, context=context):
            if rec.state<>'draft':
                raise osv.except_osv(_('Warning!'),_('You cannot delete a transfer which is not in draft state !'))
        return super(hr_holidays_timebank, self).unlink(cr, uid, ids, context)


hr_holidays_timebank()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
