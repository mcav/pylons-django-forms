"""
forms.py: Adapts Django's forms module for use with Pylons.

Copyright (c) 2009 Marcus Cavanaugh.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

Instructions:

    1. Install Django. (`easy_install django`)
    2. Read the Django Forms documentation.
    3. Pretend this module is `django.forms` and import it.

"""

__version__ = 0.1


###########################################################################
# The patches in the section below are required for django forms to work.


# Configure Django settings once, and only once.
from django.conf import settings
if not hasattr(settings, '__django_configured'):
    settings.configure()
    settings.__django_configured = True

# Django uses a function called mark_safe for HTML strings;
# adapt it to use WebHelpers' literal() function instead.
from django.utils import safestring
from webhelpers.html import literal
def webhelpers_literal(func):
    def wrapped(s):
        return literal(func(s))
    return wrapped
safestring.mark_safe = webhelpers_literal(safestring.mark_safe)

# Wildcard because this module is a drop-in replacement for `django.forms`.
from django.forms import *

# Patch widgets.SelectMultiple to work with Paste's MultiDict;
# see http://code.djangoproject.com/ticket/10659 for discussion.
def value_from_datadict_select_multiple(self, data, files, name):
    if isinstance(data, (MultiValueDict, MergeDict)):
        return data.getlist(name)
    if hasattr(data, 'getall'):   # +++
        return data.getall(name)  # +++
    return data.get(name, None)

widgets.SelectMultiple.value_from_datadict = value_from_datadict_select_multiple


# Patch fields.FileField to accommodate Pylons file handling,
# which uses cgi.FieldStorage in request.POST. This required a couple tweaks:
# First, bool(cgi.FieldStorage) is False, so you can't use "if not data" as
# FileField did. Second, cgi.FieldStorage uses data.filename and data.length
# rather than Django's data.name and data.size.
def _FileField_clean(self, data, initial=None):
        super(FileField, self).clean(initial or data)
        if not self.required and data in fields.EMPTY_VALUES:
            return None
        elif not hasattr(data, 'filename') and initial: # modified
            return initial
        
        # UploadedFile objects should have name and size attributes.
        try:
            file_name = data.filename # modified
            file_size = data.length   # modified
        except AttributeError:
            raise ValidationError(self.error_messages['invalid'])

        if self.max_length is not None and len(file_name) > self.max_length:
            error_values =  {'max': self.max_length, 'length': len(file_name)}
            raise ValidationError(self.error_messages['max_length'] % error_values)
        if not file_name:
            raise ValidationError(self.error_messages['invalid'])
        if not file_size:
            raise ValidationError(self.error_messages['empty'])
        return data
        
FileField.clean = _FileField_clean


###########################################################################
# The patches in the section below are optional, but make life easier.

# cgi.FieldStorage evaluates to False when converted to bool. That makes
# code like ``if form.cleaned_data['upload']:`` evaluate to False even
# when a valid file was uploaded. This patch changes that behavior so that
# cgi.FieldStorage evaluates to True.
import cgi
cgi.FieldStorage.__nonzero__ = lambda self: True


def model_to_dict(*items, **kwds):
    """Convert an object (like an SQLAlchemy model) or dictionary-like object
    into a dict suitable for use with Form's ``initial`` keyword.
    Additional arguments are merged into the result. Objects' attributes or
    keys beginning with an underscore, or in ``exclude``, are left out.
    
    Typical usage::
        
        c.form = ContactForm(
                    initial=forms.model_to_dict(user, {'comment_text': 'Hi'}))
    """
    exclude = kwds.pop('exclude', [])
    include = kwds.pop('include', [])
    ret = {}
    
    for item in items:
        if hasattr(item, '__dict__'): # this is a class
            item = item.__dict__
        for attr in item:
            if include and (attr not in include):
                continue
            if (attr not in exclude) and not attr.startswith('_'):
                ret[attr] = item[attr]
    return ret
    
def update_model(model, fields, **kwds):
    """Update an object (like an SQLAlchemy model) from a dictionary (like
    that provided by form.cleaned_data). Since Django's ModelForm doesn't work
    with SQLAlchemy, this is a reasonably quick alternative approach::
        
        forms.update_model(user, form.cleaned_data, exclude=['password'])

    Provide either ``exclude`` or ``include`` to further restrict which fields
    are included. Fields with an underscore are also excluded.
    """
    exclude = kwds.pop('exclude', [])
    include = kwds.pop('include', [])
    for k, v in fields.items():
        if include and (k not in include):
            continue
        if hasattr(model, k) and not callable(getattr(model, k)) and k not in exclude:
            setattr(model, k, v)
            

import formencode
from pylons import request, response

class HTMLForm(object):
    """A form that does no validation, but fills in form fields using htmlfill.
    Use this to fill in initial HTML values without doing any validation.
    See ``FormEncodeForm`` if you want to use FormEncode validation django-style.
    
    Supply the ``html`` needed to render the form (usually via your framework's
    ``render()`` method) and then pretend this is a Django Form.
    
    You can provide the ``html`` via HTMLForm's constructor, or you can 
    subclass HTMLForm and set ``html`` as a class attribute.
    
    If you sublass HTMLForm, you can still override the ``clean()`` method to 
    raise a ValidationError.
    
    Example Usage (in a controller)::
    
        def edit(self, id):
            class EditUserForm(forms.HTMLForm):
                html = render('/edit_form.html')
                
            if request.method == 'POST':
                c.form = EditUserForm(request.POST)
                if c.form.is_valid():
                    # The is_valid() call is unnecessary if you haven't
                    # overridden the HTMLForm.clean() method, since HTMLForm
                    # doesn't do any validation itself.
                    
                    # process things here
            else:
                c.form = EditUserForm() # or EditUserForm(initial=...)
        
    >>> data = {'foo': 'bar'}
    >>> form = HTMLForm(data, html='<input name="foo">')
    >>> unicode(form)
    literal(u'<input name="foo" value="bar">')
    
    >>> class MyRawHTMLForm(HTMLForm):
    ...     html = '<input type="text" name="user" value="initial in template">'
            
    >>> unicode(MyRawHTMLForm())
    literal(u'<input type="text" name="user" value="initial in template">')
    
    >>> unicode(MyRawHTMLForm(initial={'user':'john doe'}))
    literal(u'<input type="text" name="user" value="john doe">')
    """
    
    html = ''
    
    def __init__(self, data=None, files=None, html=None, initial=None):
        self.is_bound = data is not None or files is not None
        self.data = data or {}
        self.files = files or {}
        self.initial = initial or {}
        self._errors = None
        if html is not None:
            self.html = html # override the HTML for this instance instead
    
    def is_valid(self):
        self.cleaned_data = self.data
        return self.is_bound and not bool(self.errors)
        
    def clean(self):
        return self.cleaned_data
        
    def full_clean(self):
        self._errors = {}
        if not self.is_bound: # Stop further processing
            return
            
        self.cleaned_data = self.data
        try:
            self.cleaned_data = self.clean()
        except ValidationError, e:
            self._errors[forms.NON_FIELD_ERRORS] = e.messages
        if self._errors:
            delattr(self, 'cleaned_data')
        
    def _get_errors(self):
        "Returns an ErrorDict for the data provided for the form"
        if self._errors is None:
            self.full_clean()
        return self._errors
    errors = property(_get_errors)
    
    def __unicode__(self):
        # unbound forms should return the HTML unmodified. If this was passed
        # through htmlfill instead, all form values would be nuked.
        try:
            response_charset = response.determine_charset()
        except TypeError: # no pylons request is active
            response_charset = 'utf-8'
            
        if not self.is_bound:
            return literal(formencode.htmlfill.render(
                form=self.html,
                defaults=self.initial,
                errors=self.errors,
                encoding=response_charset # use the proper charset
            ))
        else:
            return literal(formencode.htmlfill.render(
                form=self.html,
                defaults=self.data,
                errors=self.errors,
                encoding=response_charset # use the proper charset
            ))

class FormEncodeForm(formencode.Schema, HTMLForm):
    """A base class for FormEncode Schemas that allows them to be processed
    just like Django Forms in your controller::
    
        def edit(self, id):
            class EditForm(forms.FormEncodeForm):
                html = render('/edit_form.html')
                text = formencode.validators.String()
                
            if request.method == 'POST':
                c.form = EditForm(request.POST)
                if c.form.is_valid():
                    # process
            else:
                c.form = EditForm()
    
    >>> class MySchema(FormEncodeForm):
    ...     html = '<form><input name="foo"></form>'
    ...     foo = formencode.validators.String(min=5)
    
    >>> form = MySchema()
    >>> unicode(form)
    literal(u'<form><input name="foo" value=""></form>')
    
    >>> form = MySchema(initial={'foo': 'hello'})
    >>> unicode(form)
    literal(u'<form><input name="foo" value="hello"></form>')
    
    >>> form = MySchema({'foo': 'bar'})
    >>> form.is_valid()
    False
    
    >>> '<input name="foo" class="error" value="bar">' in unicode(form)
    True
    """
    
    def __init__(self, *args, **kwds):
        formencode.Schema.__init__(self)
        HTMLForm.__init__(self, *args, **kwds)
    
    def full_clean(self):
        self._errors = {}
        if not self.is_bound: # Stop further processing
            return
            
        self.cleaned_data = {}
        try:
            self.cleaned_data = self.to_python(self.data)
        except formencode.validators.Invalid, e:
            self._errors = e.unpack_errors()
            
        try:
            self.cleaned_data = self.clean()
        except formencode.validators.Invalid, e:
            self._errors[forms.NON_FIELD_ERRORS] = e.unpack_errors()
        except ValidationError, e:
            self._errors[forms.NON_FIELD_ERRORS] = e.messages
        if self._errors:
            delattr(self, 'cleaned_data')

if __name__ == '__main__':
    import doctest
    doctest.testmod()