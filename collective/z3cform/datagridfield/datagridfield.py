"""
    Implementation of the widget
"""


import zope.interface
import zope.schema.interfaces
from zope.schema import getFieldsInOrder, getFieldNames
from zope.schema.interfaces import IObject, IList

from z3c.form.browser.object import ObjectWidget
from z3c.form.object import SubformAdapter, ObjectSubForm
from z3c.form.error import MultipleErrors



from five import grok

from z3c.form.browser.multi import MultiWidget
from z3c.form import interfaces

from z3c.form.interfaces import IMultiWidget, IValidator, INPUT_MODE
from z3c.form.widget import FieldWidget
from z3c.form.converter import BaseDataConverter
from z3c.form.validator import SimpleFieldValidator


class IDataGridField(IMultiWidget):
    """Grid widget."""

class DataGridFieldHandler(grok.View):
    """Handler for Ajax Calls on this widget
        This is not used.
    """
    grok.context(IDataGridField)

    def __call__(self):

        print 'DataGridFieldHandler', self.request.form

    def render(self):
        pass

class DataGridField(MultiWidget):
    """This grid should be applied to an schema.List item which has
    schema.Object and an interface"""

    zope.interface.implements(IDataGridField)

    allow_insert = True
    allow_delete = True
    auto_append = True

    def setField(self, value):
        """
            The field information is passed to the widget after it is initialised.
            Use this call to initialise the column definitions.
        """
        self._field = value

        self.columns = []
        for name, field in getFieldsInOrder(self._field.value_type.schema):
            col = {
                'name': name,
                'field': field,
                'label': field.title,
                'required': field.required,
                'mode': None,
                'callback': None, 
                'widgetFactory': None,
            }
            self.columns.append(col)

    def getField(self):
        return self._field

    field = property(getField, setField)

##     def URL(self):
##         form_url = self.request.getURL()
## 
##         form_prefix = self.form.prefix + self.__parent__.prefix
##         widget_name = self.name[len(form_prefix):]
##         return "%s/++widget++%s/@@datagridfieldhandler" % (form_url, widget_name,)
## 

    def getWidget(self, idx):
        """Create the object widget. This is used to avoid looking up the widget"""
        valueType = self.field.value_type
        if IObject.providedBy(valueType):
            widget = DataGridFieldObjectFactory(valueType, self.request)
        else:
            widget = zope.component.getMultiAdapter((valueType, self.request),
                interfaces.IFieldWidget)
        self.setName(widget, idx)

        widget.__parent__ = self

        widget.mode = self.mode
        widget.klass = 'row'
        #set widget.form (objectwidget needs this)
        if interfaces.IFormAware.providedBy(self):
            widget.form = self.form
            zope.interface.alsoProvides(
                widget, interfaces.IFormAware)
        widget.update()
        return widget

    def name_prefix(self):
        return self.prefix
    def id_prefix(self):
        return self.prefix.replace('.', '-')

    def updateWidgets(self):
        # if the field has configuration data set - copy it
        super(DataGridField, self).updateWidgets()
        if self.mode == INPUT_MODE:
            if self.auto_append:
                # If we are doing 'auto-append', then a blank row needs to be added
                widget = self.getWidget('AA')
                widget.klass = 'datagridwidget-row auto-append'
                self.widgets.append(widget)

            if self.auto_append or self.allow_insert:
                # If we can add rows, we need a template row
                template = self.getWidget('TT')
                template.klass = 'datagridwidget-row datagridwidget-empty-row'
                self.widgets.append(template)

    def setName(self, widget, idx):
        """This version facilitates inserting non-numerics"""
        widget.name = '%s.%s' % (self.name, idx)
        widget.id = '%s-%s' % (self.id, idx)

    @property
    def counterMarker(self):
        # Override this to exclude template line and auto append line
        counter = len(self.widgets)
        if self.auto_append:
            counter -= 1
        if self.auto_append or self.allow_insert:
            counter -= 1
        return '<input type="hidden" name="%s" value="%d" />' % (
            self.counterName, counter)

    def _includeRow(self, name):
        if self.mode == INPUT_MODE:
            if not name.endswith('AA') and not name.endswith('TT'):
                return True
            if name.endswith('AA'):
                return self.auto_append
            if name.endswith('TT'):
                return self.auto_append or self.allow_insert
        else:
            return not name.endswith('AA') and not name.endswith('TT')

@grok.adapter(zope.schema.interfaces.IField, interfaces.IFormLayer)
@grok.implementer(interfaces.IFieldWidget)
def DataGridFieldFactory(field, request):
    """IFieldWidget factory for DataGridField."""
    return FieldWidget(field, DataGridField(request))

class GridDataConverter(grok.MultiAdapter, BaseDataConverter):
    """Convert between the context and the widget"""
    
    grok.adapts(zope.schema.interfaces.IList, IDataGridField)
    grok.implements(interfaces.IDataConverter)

    def toWidgetValue(self, value):
        """Simply pass the data through with no change"""
        return value

    def toFieldValue(self, value):
        return value

class DataGridFieldObject(ObjectWidget):

    def isInsertEnabled(self):
        return self.__parent__.allow_insert

    def isDeleteEnabled(self):
        return self.__parent__.allow_delete

    def portal_url(self):
        return self.__parent__.context.portal_url()

    @apply
    def value():
        """I have moved this code from z3c/form/object.py because I want to allow
           a field to handle a sub-set of the schema. I filter on the subform.fields
        """
        def get(self):
            #value (get) cannot raise an exception, then we return insane values
            try:
                self.setErrors=True
                return self.extract()
            except MultipleErrors:
                value = {}
                active_names = self.subform.fields.keys()
                for name in getFieldNames(self.field.schema):
                    if name in active_names:
                        value[name] = self.subform.widgets[name].value
                return value
        def set(self, value):
            self._value = value
            self.updateWidgets()

            # ensure that we apply our new values to the widgets
            if value is not interfaces.NO_VALUE:
                active_names = self.subform.fields.keys()
                for name in getFieldNames(self.field.schema):
                    if name in active_names:
                        self.applyValue(self.subform.widgets[name],
                                    value.get(name, interfaces.NO_VALUE))

        return property(get, set)


@grok.adapter(zope.schema.interfaces.IField, interfaces.IFormLayer)
@grok.implementer(interfaces.IFieldWidget)
def DataGridFieldObjectFactory(field, request):
    """IFieldWidget factory for DataGridField."""
    return FieldWidget(field, DataGridFieldObject(request))


class DataGridFieldObjectSubForm(ObjectSubForm):
    """Local class of subform - this is intended to all configuration information
    to be passed all the way down to the subform.
    """
    def updateWidgets(self):
        rv = super(DataGridFieldObjectSubForm, self).updateWidgets()
        if hasattr(self.__parent__.form, 'datagridUpdateWidgets'):
            self.__parent__.form.datagridUpdateWidgets(self, self.widgets, self.__parent__.__parent__)
        return rv

    def setupFields(self):
        rv = super(DataGridFieldObjectSubForm, self).setupFields()
        if hasattr(self.__parent__.form, 'datagridInitialise'):
            self.__parent__.form.datagridInitialise(self, self.__parent__.__parent__)
        return rv


class DataGridFieldSubformAdapter(grok.MultiAdapter, SubformAdapter):
    """Give it my local class of subform, rather than the default"""

    grok.implements(interfaces.ISubformFactory)
    grok.adapts(zope.interface.Interface, #widget value
                          interfaces.IFormLayer,    #request
                          zope.interface.Interface, #widget context
                          zope.interface.Interface, #form
                          DataGridFieldObject,      #widget
                          zope.interface.Interface, #field
                          zope.interface.Interface) #field.schema

    factory = DataGridFieldObjectSubForm

class DataGridValidator(grok.MultiAdapter, SimpleFieldValidator):
    """
        I am crippling this validator - I return a list of dictionaries. If I don't
        cripple this it will fail because the return type is not of the correct object 
        type. For stronger typing replace both this and the converter
    """
    grok.adapts(
              zope.interface.Interface,
              zope.interface.Interface,
              zope.interface.Interface,  # Form
              IList,          # field
              DataGridField)             #widget
    grok.provides(IValidator)

    def validate(self, value):
        """
            Don't validate the table - however, if there is a cell error, make sure that
            the table widget shows it.
        """
        for subform in [widget.subform for widget in self.widget.widgets]:
            for widget in subform.widgets.values():
                if hasattr(widget, 'error') and widget.error:
                    raise ValueError(widget.label)
        return None