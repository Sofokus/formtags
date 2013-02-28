"""
Unit tests for the form tag library.
"""
from django.template import Template, Context
from django import forms

from .templatetags.forms import FormTagError

import unittest;
import re

class FormtagTests(unittest.TestCase):
    def test_catchall_only(self):
        """
        Test a single catchall matcher as the lone field.
        """
        self.__test(
            SimpleForm(),
            # Template:
            """{% field %}{{ field.name }},{% endfield %}""",
            # Expected:
            """textfield,textfield2,numberfield,numberfield2,"""
            )

    def test_field_with_catchall(self):
        """
        Test an explicit matcher together with the catchall
        """
        self.__test(
            SimpleForm(),
            # Template:
            """{% field "textfield" %}EXPLICIT,{% endfield %}
            {% field %}{{ field.name }},{% endfield %}
            """,
            # Expected:
            """EXPLICIT,textfield2,numberfield,numberfield2,"""
            )

    def test_field_after_catchall(self):
        """
        Test the two-pass field matching: explicit matcher after the catchall.
        """
        self.__test(
            SimpleForm(),
            # Template:
            """{% field %}{{ field.name }},{% endfield %}
            {% field "textfield" %}EXPLICIT{% endfield %}
            """,
            # Expected:
            """textfield2,numberfield,numberfield2,EXPLICIT"""
            )

    def test_missing_field(self):
        """
        An exception should be thrown if a field is not found
        """

        # Missing optional field should trigger no exception
        self.__test(
            SimpleForm(),
            # Template:
            """{% field "does_not_exist?" %}ERROR{% endfield %}
            {% field %}{% endfield %}""",
            # Expected:
            ""
            )
        
        # Missing required field should trigger an exception
        with self.assertRaises(FormTagError):
            self.__test(
                SimpleForm(),
                # Template:
                """{% field "does_not_exist" %}ERROR{% endfield %}
                {% field %}{% endfield %}""",
                # Expected:
                ""
                )

    def test_leftover_field(self):
        """
        An exception should be thrown if not all fields are matched.
        """
        with self.assertRaises(FormTagError):
            self.__test(
                SimpleForm(),
                # Template:
                """{% field "textfield" %}f{% endfield %}""",
                # Expected:
                "(exception expected)"
                )

    def test_wildcard(self):
        """
        Test the wildcard matcher.
        """

        # Simple test
        self.__test(
            SimpleForm(),
            # Template:
            """{% field "text*" %}{{ field.name }},{% endfield %}
            {% field %}{% endfield %}""",
            # Expected
            "textfield,textfield2,"
            )

        # Missing field test
        with self.assertRaises(FormTagError):
            self.__test(
                SimpleForm(),
                # Template:
                """{% field "nonexistent*" %}{{ field.name }},{% endfield %}
                {% field %}{% endfield %}""",
                # Expected
                "(exception expected)"
                )

        # Optional missing field test
        self.__test(
            SimpleForm(),
            # Template:
            """{% field "nonexistent*?" %}(shouldn't exist),{% endfield %}
            {% field %}{% endfield %}""",
            # Expected
            ""
            )

    def test_positional(self):
        """
        Test matching of fields before and after a named field.
        """

        # Before
        self.__test(
            SimpleForm(),
            # Template:
            """{% field "<textfield2" %}{{ field.name }},{% endfield %}
            {% field %}{% endfield %}""",
            # Expected
            "textfield,"
            )

        # This and before
        self.__test(
            SimpleForm(),
            # Template:
            """{% field "<=textfield2" %}{{ field.name }},{% endfield %}
            {% field %}{% endfield %}""",
            # Expected
            "textfield,textfield2,"
            )

        # After
        self.__test(
            SimpleForm(),
            # Template:
            """{% field ">numberfield" %}{{ field.name }},{% endfield %}
            {% field %}{% endfield %}""",
            # Expected
            "numberfield2,"
            )

        # This and after
        self.__test(
            SimpleForm(),
            # Template:
            """{% field ">=numberfield" %}{{ field.name }},{% endfield %}
            {% field %}{% endfield %}""",
            # Expected
            "numberfield,numberfield2,"
            )

    def test_precedence(self):
        """
        Check that the precedence rules are followed correctly.
        """
        self.__test(
            SimpleForm(),
            # Template:
            """
            {% field %}:1.{{ field.name }}{% endfield %}
            {% field "<=numberfield2" %}:2.{{ field.name }}{% endfield %}
            {% field ">textfield" %}:3.{{ field.name }}{% endfield %}
            {% field "numberfield*" %}:4.{{ field.name }}{% endfield %}
            {% field "numberfield2?" %}:5.{{ field.name }}{% endfield %}
            {% field "numberfield2" %}:6.{{ field.name }}{% endfield %}
            """,
            # Expected
            """
            :2.textfield
            :2.textfield2
            :4.numberfield
            :6.numberfield2
            """)

    def test_widget_name_filter(self):
        """
        The widget name filter can be used in two ways:
        * to return the name of the widget
        * to test if the widget is any of the listed
        """

        self.__test(
            SimpleForm(),
            # Template:
            """
            {% field %}{% endfield %}
            {% field "textfield" %}{{ field|widget_name }},{% endfield %}
            {% field "textfield2" %}{{ field|widget_name:"test" }},{% endfield %}
            {% field "numberfield" %}{{ field|widget_name:"TextInput test" }},{% endfield %}
            """,
            # Expected
            """
            TextInput,
            False,
            True,
            """)

    def test_choice_field(self):
        """
        Test the field_choices iterator tag
        """
        self.__test(
            ChoiceForm(initial={'choicefield': 'B'}),
            # Template:
            """
            {% field "choicefield" %}
            {% field_choices %}
            '{{ choice.value }}'='{{ choice.label }}'({{ choice.selected }}),
            {% endfield_choices %}
            {% endfield %}
            """,
            # Expected
            """
            'A'='Choice 1'(False),
            'B'='Choice 2'(True),
            'C'='Choice 3'(False),
            """)

    def test_optgroups_flat(self):
        """
        A choice_field will flatten option groups.
        """
        self.__test(
            GroupedChoiceForm(),
            # Template:
            """
            {% field "choicefield" %}
            {% field_choices %}
            {{ choice.index }}.'{{ choice.value }}'='{{ choice.label }}'
            {% endfield_choices %}
            {% endfield %}
            """,
            # Expected:
            """
            0.'0'='C0'
            1.'1'='C1'
            2.'2'='C2'
            3.'3'='C3'
            4.'4'='C4'
            """)

    def test_nested_field(self):
        """
        Test the nesting of two form fields.
        """
        self.__test(
            ChoiceForm2(),
            # Template:
            """
            {% field "choicefield" %}{{ field.name }}
                {% field "textfield" %}:{{ field.name }}:{% endfield %}
            {% field_choices %}{{ choice.value }};{% endfield_choices %}
            {% hidden_fields %}
            {{ field.name }}
            {% endfield %}
            {% field %}{% endfield %}
            """,
            # Expected:
            """
            choicefield
            :textfield:
            A;B;
            choicefield
            """)

    def __test(self, form, template, expected):
        return self.assertEquals(
            _strip(_render(''.join((
                "{% load forms %}{% form form %}",
                template,
                '{% endform %}')),
                form=form)),
            _strip(expected)
            )

class SimpleForm(forms.Form):
    textfield = forms.CharField()
    textfield2 = forms.CharField()
    numberfield = forms.IntegerField()
    numberfield2 = forms.IntegerField()
    hidden1 = forms.IntegerField(widget=forms.HiddenInput())

class ChoiceForm(forms.Form):
    choicefield = forms.ChoiceField(choices=(
        ('A', 'Choice 1'),
        ('B', 'Choice 2'),
        ('C', 'Choice 3'),
        ))

class ChoiceForm2(forms.Form):
    textfield = forms.CharField()
    choicefield = forms.ChoiceField(choices=(
        ('A', 'Choice 1'),
        ('B', 'Choice 2'),
        ))

class GroupedChoiceForm(forms.Form):
    choicefield = forms.ChoiceField(choices=(
        ('0', 'C0'),
        ('GA', (
            ('1', 'C1'),
            ('2', 'C2'),
        )),
        ('GB', (
            ('3', 'C3'),
            ('4', 'C4'),
        )),
        ))

def _strip(text):
    return re.sub(r'\s', '', text)

def _render(template, **kwargs):
    tpl = Template(template)
    c = Context(kwargs)
    return tpl.render(c)

