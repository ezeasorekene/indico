# This file is part of Indico.
# Copyright (C) 2002 - 2017 European Organization for Nuclear Research (CERN).
#
# Indico is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of the
# License, or (at your option) any later version.
#
# Indico is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Indico; if not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals

import mimetypes
from collections import OrderedDict
from datetime import datetime
from operator import itemgetter

import wtforms
from werkzeug.datastructures import FileStorage
from wtforms.validators import NumberRange, ValidationError, InputRequired

from indico.modules.events.registration.fields.base import (RegistrationFormFieldBase, RegistrationFormBillableField)
from indico.util.date_time import strftime_all_years
from indico.util.fs import secure_filename
from indico.util.i18n import _, L_
from indico.util.string import normalize_phone_number
from indico.web.forms.fields import IndicoRadioField
from indico.web.forms.validators import IndicoEmail
from MaKaC.webinterface.common.countries import CountryHolder


class TextField(RegistrationFormFieldBase):
    name = 'text'
    wtf_field_class = wtforms.StringField


class NumberField(RegistrationFormBillableField):
    name = 'number'
    wtf_field_class = wtforms.IntegerField
    required_validator = InputRequired

    @property
    def validators(self):
        min_value = self.form_item.data.get('min_value', None)
        return [NumberRange(min=min_value)] if min_value else None

    def calculate_price(self, reg_data, versioned_data):
        if not versioned_data.get('is_billable'):
            return 0
        return versioned_data.get('price', 0) * int(reg_data or 0)

    def get_friendly_data(self, registration_data, for_humans=False):
        if registration_data.data is None:
            return ''
        return str(registration_data.data) if for_humans else registration_data.data


class TextAreaField(RegistrationFormFieldBase):
    name = 'textarea'
    wtf_field_class = wtforms.StringField


class CheckboxField(RegistrationFormBillableField):
    name = 'checkbox'
    wtf_field_class = wtforms.BooleanField
    friendly_data_mapping = {None: '',
                             True: L_('Yes'),
                             False: L_('No')}

    def calculate_price(self, reg_data, versioned_data):
        if not versioned_data.get('is_billable') or not reg_data:
            return 0
        return versioned_data.get('price', 0)

    def get_friendly_data(self, registration_data, for_humans=False):
        return self.friendly_data_mapping[registration_data.data]

    def get_places_used(self):
        places_used = 0
        if self.form_item.data.get('places_limit'):
            for registration in self.form_item.registration_form.active_registrations:
                if self.form_item.id not in registration.data_by_field:
                    continue
                if registration.data_by_field[self.form_item.id].data:
                    places_used += 1
        return places_used

    @property
    def view_data(self):
        return dict(super(CheckboxField, self).view_data, places_used=self.get_places_used())

    @property
    def filter_choices(self):
        return {unicode(val).lower(): caption for val, caption in self.friendly_data_mapping.iteritems()
                if val is not None}

    @property
    def validators(self):
        def _check_number_of_places(form, field):
            if form.modified_registration:
                old_data = form.modified_registration.data_by_field.get(self.form_item.id)
                if not old_data or not self.has_data_changed(field.data, old_data):
                    return
            if field.data and self.form_item.data.get('places_limit'):
                places_left = self.form_item.data.get('places_limit') - self.get_places_used()
                if not places_left:
                    raise ValidationError(_('There are no places left for this option.'))
        return [_check_number_of_places]

    @property
    def default_value(self):
        return None


class DateField(RegistrationFormFieldBase):
    name = 'date'
    wtf_field_class = wtforms.StringField

    def process_form_data(self, registration, value, old_data=None, billable_items_locked=False):
        if value:
            date_format = self.form_item.data['date_format']
            value = datetime.strptime(value, date_format).isoformat()
        return super(DateField, self).process_form_data(registration, value, old_data, billable_items_locked)

    def get_friendly_data(self, registration_data, for_humans=False):
        date_string = registration_data.data
        if not date_string:
            return ''
        dt = datetime.strptime(date_string, '%Y-%m-%dT%H:%M:%S')
        return strftime_all_years(dt, self.form_item.data['date_format'])

    @property
    def view_data(self):
        has_time = ' ' in self.form_item.data['date_format']
        return dict(super(DateField, self).view_data, has_time=has_time)


class BooleanField(RegistrationFormBillableField):
    name = 'bool'
    wtf_field_class = IndicoRadioField
    required_validator = InputRequired
    friendly_data_mapping = {None: '',
                             True: L_('Yes'),
                             False: L_('No')}

    @property
    def wtf_field_kwargs(self):
        return {'choices': [(True, _('Yes')), (False, _('No'))],
                'coerce': lambda x: {'yes': True, 'no': False}.get(x, None)}

    @property
    def filter_choices(self):
        return {unicode(val).lower(): caption for val, caption in self.friendly_data_mapping.iteritems()
                if val is not None}

    @property
    def view_data(self):
        return dict(super(BooleanField, self).view_data, places_used=self.get_places_used())

    @property
    def validators(self):
        def _check_number_of_places(form, field):
            if form.modified_registration:
                old_data = form.modified_registration.data_by_field.get(self.form_item.id)
                if not old_data or not self.has_data_changed(field.data, old_data):
                    return
            if field.data and self.form_item.data.get('places_limit'):
                places_left = self.form_item.data.get('places_limit') - self.get_places_used()
                if field.data and not places_left:
                    raise ValidationError(_('There are no places left for this option.'))
        return [_check_number_of_places]

    @property
    def default_value(self):
        return None

    def get_places_used(self):
        places_used = 0
        if self.form_item.data.get('places_limit'):
            for registration in self.form_item.registration_form.active_registrations:
                if self.form_item.id not in registration.data_by_field:
                    continue
                if registration.data_by_field[self.form_item.id].data:
                    places_used += 1
        return places_used

    def calculate_price(self, reg_data, versioned_data):
        if not versioned_data.get('is_billable'):
            return 0
        return versioned_data.get('price', 0) if reg_data else 0

    def get_friendly_data(self, registration_data, for_humans=False):
        return self.friendly_data_mapping[registration_data.data]


class PhoneField(RegistrationFormFieldBase):
    name = 'phone'
    wtf_field_class = wtforms.StringField
    wtf_field_kwargs = {'filters': [lambda x: normalize_phone_number(x) if x else '']}


class CountryField(RegistrationFormFieldBase):
    name = 'country'
    wtf_field_class = wtforms.SelectField

    @property
    def wtf_field_kwargs(self):
        return {'choices': sorted(CountryHolder.getCountries().items(), key=itemgetter(1))}

    @classmethod
    def unprocess_field_data(cls, versioned_data, unversioned_data):
        choices = sorted([{'caption': v, 'countryKey': k} for k, v in CountryHolder.getCountries().iteritems()],
                         key=itemgetter('caption'))
        return {'choices': choices}

    @property
    def filter_choices(self):
        return OrderedDict(self.wtf_field_kwargs['choices'])

    def get_friendly_data(self, registration_data, for_humans=False):
        return CountryHolder.getCountryById(registration_data.data) if registration_data.data else ''


class _DeletableFileField(wtforms.FileField):
    def process_formdata(self, valuelist):
        if not valuelist:
            self.data = {'keep_existing': False, 'uploaded_file': None}
        else:
            # This expects a form with a hidden field and a file field with the same name.
            # If the hidden field is empty, it indicates that an existing file should be
            # deleted or replaced with the newly uploaded file.
            keep_existing = '' not in valuelist
            uploaded_file = next((x for x in valuelist if isinstance(x, FileStorage)), None)
            if not uploaded_file or not uploaded_file.filename:
                uploaded_file = None
            self.data = {'keep_existing': keep_existing, 'uploaded_file': uploaded_file}


class FileField(RegistrationFormFieldBase):
    name = 'file'
    wtf_field_class = _DeletableFileField

    def process_form_data(self, registration, value, old_data=None, billable_items_locked=False):
        data = {'field_data': self.form_item.current_data}
        file_ = value['uploaded_file']
        if file_:
            # we have a file -> always save it
            data['file'] = {
                'data': file_.file,
                'name': secure_filename(file_.filename, 'attachment'),
                'content_type': mimetypes.guess_type(file_.filename)[0] or file_.mimetype or 'application/octet-stream'
            }
        elif not value['keep_existing']:
            data['file'] = None
        return data

    @property
    def default_value(self):
        return None

    def get_friendly_data(self, registration_data, for_humans=False):
        if not registration_data:
            return ''
        return registration_data.filename


class EmailField(RegistrationFormFieldBase):
    name = 'email'
    wtf_field_class = wtforms.StringField
    wtf_field_kwargs = {'filters': [lambda x: x.lower() if x else x]}

    @property
    def validators(self):
        return [IndicoEmail()]
