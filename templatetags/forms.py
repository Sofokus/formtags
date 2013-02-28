"""
Tag library for simplifying custom form rendering in Django templates.
Version 1.0
Copyright 2013 Sofokus Oy. Licensed under the MIT license.
---

This library introduces four new tags and one filter:

    {% form name %} ... {% endform %}
    {% field ["matcher"...] [as field] %} ... {% endfield %}
    {% field_choices [as choice] %}...{% empty %}...{% endfield_choices %}
    {% hidden_fields %}
    {{ field|widget_name }}

The form tag defines the scope for the form fields. The first
parameter is the context variable containing the Django form.

The field tag loops over all visible form fields that match the given
constraints.

Here is a simple example that renders all the form fields in the same style:
    {% form form %}
    {% field %}
    <div>
    <p>{{ field.label }}</p>
    <p>{{ field }} {{ field.errors }}</p>
    </div>
    {% endfield %}
    {% endform %}

As the field tag only loops through visibile fields, you typically want
to include something like this as well:

    {% for hidden in form.hidden_fields %}
    {{ hidden }}
    {% endfor %}

For convenience, this is included as a prepackaged tag:

    {% hidden_fields %}

To render custom choice fields, the field_choices tag can be used:

    {% field "mychoicefield" %}
    {% field_choices %}
    <p><input type="checbox" name="{{ field.name }}"
        id="{{ choice.id }}" {{ choice.checked }} value="{{ choice.value }}">
    <label for="{{ choice.id }}">{{ choice.label }}</label>
    </p>
    {% empty %}
    no choices!
    {% endfield_choices %}
    {% endfield %}
    
Of course, the real power of this tag library is in the field matchers.

This example renders the field named "title" first, followed by the rest of
the fields:
    {% form %}
        {% field "title" %}...{% endfield %}
        {% field %}...{% endfield %}
    {% endform

More specific field matchers have precedence over more general matchers, so
in the above example the uniquely identifying matcher "title" could have
come after the catch-all field tag. This is accomplished by rendering the form
in two passes: During the first pass the field tags sort themselves according
to their precedence and grab all the fields they can. Any output generated
during the first pass is discarded. The second pass is when the fields, now
knowing their proper order, actually render their contents.

Field tags may also be nested. For example:
    {% form %}
    {% field "title" %}
        <div>
        {{ field }}
        {% field "subtitle" %}
            {{ field }}
        {% endfield %}
        </div>
    {% endfield %}
    {% endform %}

The following matchers are supported (listed in order of precedence, from high
to low):

    "name"      --  Match the field with the given name. If the field does not
                    exist, an error is generated.
    "name?"     --  Like above, but missing fields are silently ignored.
    "name*"     --  Match all fields starting with the given substring. If no
                    fields are matched, an error is generated.
    "name*?"    --  Like above, but no error is generated even if no field
                    matches.
    "<name"     --  Match all fields that come before "name".
    "<=name"    --  Match "name" and all fields that come before it.
    ">name"     --  Match all fields that come after "name".
    ">=name"    --  Match "name" and all fields that come after it.

                --  If no matcher is explicitly given, all remaining fields (if
                    any) will be matched.

In addition to the tags, the following filters are provided:

    {{ field|widget_name[:"name1 name2 ..."] }}

The widget_name filter returns the name of the field's widget class.
It is useful for rendering fields differently based on their type.
To facilitate this use case, it can accept a space separated list of
widget names as an argument and return True if any of them match.

Example:
    {% if field|widget_name:"Textarea MyBigWidget" %}
    ...
    {% else %}
    ...
    {% endif %}


"""

from collections import deque
from django import template

register = template.Library()

# The form instance will available here, regardless
# of the original name
FORMVAR = "__FORMS_FORM"

# The current form field will be available here, in
# addition to the normal public variable (typically "field")
CURFIELDVAR = "__FORMS_FIELD"

# The actual form fields will be made available here.
# They are packed into tuples, one for each tag.
FIELDSVAR = "__FORMS_FIELDS"

# Field tags register their matchers here for sorting.
FTAGSVAR = "__FORMS_FIELDTAGS"

# Form rendering state.
# This is either 0 for field gathering or 1 for final rendering.
STATEVAR = "__FORMS_STATE"

class FormTagError(template.TemplateSyntaxError):
    pass

class FieldMatcher(object):
    """
    Base class for field matchers.
    """

    def __init__(self, defstr):
        self.definition_string = defstr

    def match(self, field, field_order):
        """
        Return true if the given field is matched by this object.

        Arguments
        field       --  the form field instance to test
        field_order --  map of field names to index numbers
        """
        raise NotImplementedError("Matcher not implemented!")

    def is_required(self):
        """
        Return true if it is an error if this matcher does not match any
        field.

        This is a debugging aid for catching forgotten or mispelled fields
        in the template. For some fields (e.g. the catch-all field) not
        matching anything is acceptable.
        """
        return True

    def precedence(self):
        """
        During field assignment, field tags will greedily grab all the
        form fields they can in the order of their precedence. Lower number
        means higher precedence.
        """
        raise NotImplementedError("No precedence given for field!")

    def __repr__(self):
        return '{}({})'.format(type(self).__name__, self.definition_string)

class AnyMatcher(FieldMatcher):
    """
    A matcher that matches any field.
    """

    def __init__(self):
        super(AnyMatcher, self).__init__('')

    def match(self, field, field_order):
        return True

    def is_required(self):
        return False

    def precedence(self):
        return 99

class NameMatcher(FieldMatcher):
    """
    A matcher that matches fields by name.

    Currently, we support simple wildcard matching.
    If the matcher ends with *, the name matches the prefix
    of the form field. A wildcard matcher has lower precedence
    than a non-wildcard name matcher.
    """
    def __init__(self, name):
        super(NameMatcher, self).__init__(name)

        if name[-1] == '*':
            self.wildcard = True
            self.name = name[:-1]
        else:
            self.wildcard = False
            self.name = name

    def match(self, field, field_order):
        if self.wildcard:
            return field.name.startswith(self.name)
        else:
            return field.name == self.name

    def precedence(self):
        return 0 if not self.wildcard else 10

class OptionalNameMatcher(NameMatcher):
    """
    A name matcher that ignores missing fields.
    
    An optional name matcher has lower precendence than
    a required one."""

    def is_required(self):
        return False

    def precedence(self):
        return super(OptionalNameMatcher, self).precedence() + 1

class RelativeMatcher(FieldMatcher):
    """
    A matcher that matches all fields before or after a specified field.
    Supported operands are:
    <  - match all fields before the operand
    >  - match all fields after the operand
    <= - match the operand and all fields before it
    >= - match the operand and all fields after it
    """
    def __init__(self, operator, operand):
        super(RelativeMatcher, self).__init__(operator + operand)
        self.operand = operand
        self.op = operator
        if operator == '<':
            self.operator = lambda x, y: x < y
        elif operator == '<=':
            self.operator = lambda x, y: x <= y
        elif operator == '>':
            self.operator = lambda x, y: x > y
        elif operator == '>=':
            self.operator = lambda x, y: x >= y
        else:
            raise FormTagError("Unknown operator: {}".format(operator))

    def match(self, field, field_order):
        try:
            return self.operator(field_order[field.name], field_order[self.operand])
        except KeyError:
            raise FormTagError("No such field: {}".format(self.operand))

    def is_required(self):
        return False

    def precedence(self):
        return 50 if self.op[0] == '<' else 60

def _assign_fields(form, fieldlist):
    """
    Return a list of fields from the given form matched by the matchers.
    The returned value will be a list of tuples corresponding to the list
    of matchers. The matchers will be applied in order of their precedence.
    For optional matchers, the corresponding tuples may be empty.

    Arguments:
    form      -- the form whose fields to match
    fieldlist -- list of field matchers

    """

    # Sort matcher list in order of precedence, but remember
    # the original order too
    matcher_list = []
    for i, matchers in enumerate(fieldlist):
        for m in matchers:
            matcher_list.append((i, m.precedence(), m))

    matcher_list.sort(key=lambda m: m[1])

    # Let the sorted matchers greedily grab all the fields they can.
    # The results are stored in the original order.
    fields = form.visible_fields()
    field_order = {f.name : idx for (idx, f) in enumerate(fields)}

    assigned = deque([[] for x in range(len(fieldlist))])
    for m in matcher_list:
        assigned[m[0]].extend(_take(fields, field_order, m[2]))

    # Done. Left over fields indicate a bug in the template.
    if len(fields) > 0:
        raise FormTagError("{} form field(s) left over!".format(len(fields)))

    return assigned

def _take(fields, field_order, matcher):
    """
    Take matching fields from the list.

    The elements are removed from the list and returned
    as a new list.

    Arguments:
    fields      -- the list of fields to process
    field_order -- map of field name to original index number
    matcher     -- the matcher to apply to each list element.

    """
    matched = []
    for f in fields:
        if matcher.match(f, field_order):
            matched.append(f)

    if len(matched) > 0:
        fields[:] = filter(lambda f: f not in matched, fields)

    elif matcher.is_required():
        raise FormTagError("Matcher {!r} did not match any field!".format(matcher))

    return matched

class FormNode(template.Node):
    """
    Container node for fields.

    Form nodes can be nested.
    """
    def __init__(self, nodelist, form):
        self.nodelist = nodelist
        self.form = form

    def render(self, context):
        context.push()

        # Gather fields
        context[FORMVAR] = context[self.form]
        context[STATEVAR] = 0
        context[FTAGSVAR] = []
        self.nodelist.render(context)

        # Assign fields to tags, taking matcher precedence in account
        assigned = _assign_fields(context[self.form], context[FTAGSVAR])
        context[FIELDSVAR] = assigned

        # Render
        context[STATEVAR] = 1
        out = self.nodelist.render(context)
        
        context.pop()

        return out

    def __repr__(self):
        return '<Form node: {}>'.format(self.form)

class FieldNode(template.Node):
    """
    Render all fields matched by this tag.

    Field tags can be nested, but the parent field may match only
    one field!
    """
    def __init__(self, nodelist, fieldvar, matchers):
        self.nodelist = nodelist
        self.__matchers = matchers
        self.__fieldvar = fieldvar
        self.__has_nested = len(self.get_nodes_by_type(FieldNode)) > 1

    def render(self, context):
        if STATEVAR not in context:
            raise FormTagError("Field tag must be nested in a form tag!")

        if context[STATEVAR] == 0:
            # State 0: Field gathering.

            matchers = []
            if not self.__matchers:
                matchers.append(AnyMatcher())

            for mvar in self.__matchers:
                m = mvar.resolve(context)

                if m[0] == '>' or m[0] == '<':
                    if m[1]=='=':
                        matchers.append(RelativeMatcher(m[0:2], m[2:]))
                    else:
                        matchers.append(RelativeMatcher(m[0], m[1:]))
                elif m[-1] == '?':
                    matchers.append(OptionalNameMatcher(m[0:-1]))
                else:
                    matchers.append(NameMatcher(m))

            context[FTAGSVAR].append(matchers)

            # If nested fields are present, we must render the content
            # so they can register themselves as well
            if self.__has_nested:
                return self.nodelist.render(context)
            else:
                return u''

        else:
            # State 1: Render assigned fields.
            fields = context[FIELDSVAR].popleft()

            context.push()
            out = []
            for f in fields:
                context[self.__fieldvar] = f
                context[CURFIELDVAR] = f
                out.append(self.nodelist.render(context))
            context.pop()

            return u'\n'.join(out)

    def __repr__(self):
        return '<Field node: {}>'.format(', '.join(repr(m) for m in self.__matchers))

class FieldChoicesNode(template.Node):
    """
    A convenience tag for looping through all the choices of a field.
    It adds a variable "choice" to to its scope. The choice variable
    is a dictionary containing the following items:
    
    value    -- the value of the current choice
    label    -- the label text of the current choice
    selected -- True if the current choice is selected, otherwise False
    checked  -- "checked=checked" if selected is True, otherwise empty
    index    -- The index number of the option (0-based)
    id       -- ID for the choice item

    Note. Option groups will be flattened.

    If there are no choices, the {% empty %} block (if present) will be
    rendered.
    """

    def __init__(self, nodelists, choice_var):
        self.nodelists = nodelists
        self.choice_var = choice_var
        
    def render(self, context):
        if context[STATEVAR] == 0:
            return u''

        field = context[CURFIELDVAR]
        form = context[FORMVAR]

        out = []
        context.push()

        d = getattr(field.field, 'data', form.initial.get(field.name, None))

        def _render_choice(value, label, idx):
            selected = d and value in d
            context[self.choice_var] = {
                'value': value,
                'label': label,
                'selected': selected,
                'checked': 'checked=checked' if selected else '',
                'index': idx,
                'id': '{}_{}'.format(field.auto_id, idx),
            }
            out.append(self.nodelists[0].render(context))

        choice_index = 0
        if field.field.choices:
            for cval, clbl in field.field.choices:
                if isinstance(clbl, (tuple, list)):
                    for val, lbl in clbl:
                        _render_choice(val, lbl, choice_index)
                        choice_index += 1

                else:
                    _render_choice(cval, clbl, choice_index)
                    choice_index += 1

        elif len(self.nodelists) > 1:
            out.append(self.nodelists[1].render(context))
            
        context.pop()

        return u''.join(out)

    def __repr__(self):
        return '<FieldChoicesNode node: {}>'.format(self.val_var)
            
class HiddenFieldsNode(template.Node):
    """
    A convenience tag that renders all the hidden form fields.
    Pretty much the equivalent of
    {% for hidden in form.hidden_fields %}
    {{ hidden }}
    {% endfor %}

    This tag has the following advantages over the above snippet:
    1. It is shorter to type
    2. It automatically uses the correct form from the enclosing tag
    3. It is slightly more efficient
    """
    def render(self, context):
        if FORMVAR not in context:
            raise FormTagError("Hidden field tag must be nested in a form tag!")

        if context[STATEVAR] == 1:
            return u'\n'.join([unicode(f) for f in context[FORMVAR].hidden_fields()])
        else:
            return u''

    def __repr__(self):
        return '<Hidden fields node>'

@register.tag
def form(parser, token):
    try:
        tag_name, form_var = token.split_contents()
        nodelist = parser.parse(('endform',))
        parser.delete_first_token()
    except ValueError:
        raise FormTagError("{} tag requires a single argument".format(token.contents.split()[0]))

    return FormNode(nodelist, form_var)

@register.tag
def field(parser, token):
    tokens = token.split_contents()[1:]
    fieldvar = 'field'
    if len(tokens)>=2:
        if tokens[-2] == 'as':
            fieldvar = tokens[-1]
            tokens = tokens[:-2]

    nodelist = parser.parse(('endfield',))
    parser.delete_first_token()

    return FieldNode(nodelist, fieldvar, [parser.compile_filter(t) for t in tokens])

@register.tag
def field_choices(parser, token):
    tokens = token.split_contents()[1:]

    choice_var = 'choice'

    if len(tokens) == 2 and tokens[0] == 'as':
        choice_var = tokens[1]
        
    elif len(tokens) != 0:
        raise FormTagError("field_choices takes 0 or 2 arguments: [as <choice var>]")

    nodelists = [parser.parse(('endfield_choices', 'empty'))]
    token = parser.next_token()
    if token.contents == 'empty':
        nodelists.append(parser.parse(('endfield_choices',)))
        parser.next_token()

    return FieldChoicesNode(nodelists, choice_var)
    
@register.tag
def hidden_fields(parser, token):
    return HiddenFieldsNode()

@register.filter
def widget_name(field, match_names=None):
    """
    Filter: Return the name of the widget class of the given field.

    The filter can be passed a space separated list of class name as an
    argument. In this case the filter will return True if any of the names
    match the widget class name and False if not.
    """
    name = type(field.field.widget).__name__
    if match_names:
        for a in match_names.split():
            if name == a:
                return True
        return False
    return name

