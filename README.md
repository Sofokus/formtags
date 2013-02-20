Sofokus Formtags
================

Installation
-------------

Simply place the formtags app in your project path and include it in the
`INSTALLED_APPS` list in `settings.py`.
Alternatively, you can copy the `forms.py` file to the `templatetags`
directory of an app already in your project.

Usage
------

Sofokus Formtags is a tag library for Django that simplifies the
task of generating customized form HTML. Think of it as a smart {% for %} tag.

To use the formtags library, include the command `{% load forms %}` in the
template.

A trivial example:

	:::django
		{% load forms %}
		{% form form %}
		{% field %}(render form field){% endfield %}
		{% endform %}

This is equivalent to:

	:::django
		{% for field in form %}
		(render form field)
		{% endforeach %}

Now, what if you want to change the rendering of a single field, but the
built-in output is good enough for the rest? With the standard form
tag, you're out of luck. With formtags, it's this easy:

	:::django
		{% form %}
		{% field "my_special_field" %}
		(custom rendering)
		{% endfield %}
		{% field %}
		( standard rendering )
		{% endfield %}
		{% endform %}

OK, but what if the field you want to change is in the middle of the form?
We can use matchers:

	:::django
		{% form %}
		{% field "<my_special_field" %}
		( standard rendering )
		{% endfield %}
		{% field "my_special_field" %}
		(custom rendering)
		{% endfield %}
		{% field %}
		( standard rendering )
		{% endfield %}
		{% endform %}

The `{% field %}` tag with no matcher is the catchall field that handles all
the fields left over. The form is rendered in two passes, each matcher having
a specific precedence. Thus this works too:

	:::django
		{% form %}
		{% field %}
		( standard rendering )
		{% endfield %}
		{% field "my_special_field" %}
		(custom rendering)
		{% endfield %}
		{% endform %}

For a full list of tags and filters included, refer to the documentation in
the forms.py file.

Fixing bugs and adding features
--------------------------------

When fixing a bug you have discovered, start by creating a unit test in
`tests.py` that reproduces the problem. This will help you determine when the
bug is truly fixed and, most importantly, guard against future regressions.

The same applies when adding a new feature. Start with the test cases, then
implement the feature.

