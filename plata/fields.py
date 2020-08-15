import datetime
import decimal
import logging
import simplejson as json

from django import forms
from django.db import models
from django.utils.functional import curry
from django.utils.translation import ugettext_lazy as _

import plata


try:
    json.dumps([42], use_decimal=True)
except TypeError:
    raise Exception('simplejson>=2.1 with support for use_decimal required.')


#: Field offering all defined currencies
CurrencyField = curry(models.CharField, _('currency'), max_length=3, choices=list(zip(
    plata.settings.CURRENCIES, plata.settings.CURRENCIES)))


def json_encode_default(o):
    # See "Date Time String Format" in the ECMA-262 specification.
    import datetime
    if isinstance(o, datetime.datetime):
        r = o.isoformat()
        if o.microsecond:
            r = r[:23] + r[26:]
        if r.endswith('+00:00'):
            r = r[:-6] + 'Z'
        return r
    elif isinstance(o, datetime.date):
        return o.isoformat()
    elif isinstance(o, datetime.time):
        if is_aware(o):
            raise ValueError("JSON can't represent timezone-aware times.")
        r = o.isoformat()
        if o.microsecond:
            r = r[:12]
        return r
    elif isinstance(o, decimal.Decimal):
        return str(o)

    raise TypeError('Cannot encode %r' % o)


class JSONFormField(forms.fields.CharField):
    def clean(self, value, *args, **kwargs):
        if value:
            try:
                # Run the value through JSON so we can normalize formatting and at least learn about malformed data:
                value = json.dumps(json.loads(value, use_decimal=True),
                    default=json_encode_default, use_decimal=True)
            except ValueError:
                raise forms.ValidationError("Invalid JSON data!")

        return super(JSONFormField, self).clean(value, *args, **kwargs)


class JSONField(models.TextField, metaclass=models.SubfieldBase):
    """
    TextField which transparently serializes/unserializes JSON objects

    See:
    http://www.djangosnippets.org/snippets/1478/
    """

    formfield = JSONFormField

    def to_python(self, value):
        """Convert our string value to JSON after we load it from the DB"""

        if isinstance(value, dict):
            return value
        elif isinstance(value, str):
            # Avoid asking the JSON decoder to handle empty values:
            if not value:
                return {}

            try:
                return json.loads(value, use_decimal=True)
            except ValueError:
                logging.getLogger("plata.fields").exception("Unable to deserialize store JSONField data: %s", value)
                return {}
        else:
            assert value is None
            return {}

    def get_prep_value(self, value):
        """Convert our JSON object to a string before we save"""
        return self._flatten_value(value)

    def value_to_string(self, obj):
        """Extract our value from the passed object and return it in string form"""

        if hasattr(obj, self.attname):
            value = getattr(obj, self.attname)
        else:
            assert isinstance(obj, dict)
            value = obj.get(self.attname, "")

        return self._flatten_value(value)

    def _flatten_value(self, value):
        """Return either a string, JSON-encoding dict()s as necessary"""
        if not value:
            return ""

        if isinstance(value, dict):
            value = json.dumps(value, default=json_encode_default,
                use_decimal=True)

        assert isinstance(value, str)

        return value

    def value_from_object(self, obj):
        return json.dumps(super(JSONField, self).value_from_object(obj),
            default=json_encode_default, use_decimal=True)


try:
    from south.modelsinspector import add_introspection_rules

    JSONField_introspection_rule = ( (JSONField,), [], {}, )

    add_introspection_rules(rules=[JSONField_introspection_rule], patterns=["^plata\.fields"])
except ImportError:
    pass
