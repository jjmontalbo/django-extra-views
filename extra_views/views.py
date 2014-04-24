import types
from django.utils.translation import ugettext_lazy as _
from django.core.exceptions import ImproperlyConfigured
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.shortcuts import redirect
from django.views.generic import ListView


class MultiFormMixin(object):
    """
    Allows processing of multiple model forms and multiple model formsets that
    relate to a master model via `ForeignKey`.

    This mixin must almost always be partnered with `django.views.generic.CreateView`
    or `django.views.generic.UpdateView`.

    The extra forms and formsets will be passed into the template context as sequences as
    `extra_forms` and `extra_formsets`, respectively. The form for the master model
    will still be referred to as `form`.

    Example:

    class ACreateView(MultiFormMixin, CreateView):
        model = A  # The master model
        form_class = AForm  # Model form for master model

        # Dictionary of additional model forms that relate to the master model.
        # You can alternatively define a method `get_extra_form_classes` that
        # returns a dictionary in the same format given below.
        # If ordering of these extra forms is not necessary, you can use
        # a normal dictionary instead of an OrderedDict.
        extra_form_classes = OrderedDict()
        extra_form_classes['b1_form'] = {
            'instance': lambda self: self.get_object().b1,  # required. Instance of B1 model that has a relationship with A
            'foreign_key_field': 'a',  # required. Attribute in B1 that is the foreign key to A
            'form_class': B1Form,  # required. Class of model form for B1 to be used

            # Optional. To be passed as kwargs when form_class above is instantiated.
            # `key` will be the name of the attribute.
            # Append `__callable` to the key name to indicate that its value is a callable accepting an instance of this view.
            'kwargs': {
                #...
            },

            # Other items can be added here. These added items will be accessible to the template with {{ form.settings.additional_attribute }},
            # Where `additional_attribute` is a key in this dictionary.
        }

        # Dictionary of additional model formsets that relate to the master model (i.e., inline model formsets).
        # You can alternatively define a method `get_extra_formset_classes` that
        # returns a dictionary in the same format given below.
        # If ordering of these extra forms is not necessary, you can use
        # a normal dictionary instead of an OrderedDict.
        extra_formset_classes = OrderedDict()
        extra_formset_classes['b2_formset'] = {
            'form_class': B2FormSet,  # instance of the class for the model formset

            # Optional. To be passed as kwargs when formset_class above is instantiated.
            # `key` will be the name of the attribute.
            # Append `__callable` to the key name to indicate that its value is a callable accepting an instance of this view.
            # Note that these kwargs will be passed to the formset_class's constructor,
            # AND NOT TO THE FORMS CONTAINED (OR WILL BE CONTAINED) IN IT. It is up to you to pass these
            # to those forms.
            'kwargs': {
                #...
            },

            # Other items can be added here. These added items will be accessible to the template with {{ form.settings.additional_attribute }},
            # Where `additional_attribute` is a key in this dictionary.
        }

    """
    def get_extra_form_classes(self):
        """
        Returns a dictionary containing information for additional forms.

        The dictionary returned has the form's name as its key, and mapping
        to a dictionary with settings for the form.

        """
        if hasattr(self, 'extra_form_classes'):
            return self.extra_form_classes
        return {}

    def get_formset_classes(self):
        """
        Returns a dictionary containing information for formsets.

        The dictionary returned has the formset's name as its key, and mapping
        to a dictionary with settings for the formset.

        """
        if hasattr(self, 'formset_classes'):
            return self.formset_classes
        return {}

    def _get_forms(self, form_classes, is_formset):
        extra_forms = []
        for name, form_data in form_classes.items():
            prefix = name
            form_class = form_data.get('form_class', form_data.get('formset_class', None))
            if not form_class:
                raise ImproperlyConfigured('`form_class` is required for `%s`.' % name)
            if isinstance(form_class, types.FunctionType):
                form_class = form_class(self)
            # This second check is to see if the callable returned something.
            if not form_class:
                raise TypeError('Calling `form_class` did not return anything for `%s`.' % name)

            form_class_kwargs = {
                'prefix': prefix
            }

            if self.request.method == 'POST':
                form_class_kwargs['data'] = self.request.POST
                form_class_kwargs['files'] = self.request.FILES

            # Assign the instance.
            instance = form_data.get('instance', None)
            if not is_formset and instance and callable(instance):
                instance = instance(self)
            elif is_formset:
                instance = self.object
            else:
                instance = None
            form_class_kwargs['instance'] = instance

            try:
                kwargs = form_data['kwargs']
                final_kwargs = {}
                for k, v in kwargs.items():
                    if k.endswith('__callable'):
                        final_kwargs[k[:-len('__callable')]] = v(self)
                    else:
                        final_kwargs[k] = v
                form_class_kwargs.update(final_kwargs)
            except KeyError:
                pass

            form = form_class(**form_class_kwargs)
            form.settings = form_data
            extra_forms.append(form)
        return extra_forms

    def get_extra_forms(self):
        if not hasattr(self, '_extra_forms'):
            self._extra_forms = self._get_forms(self.get_extra_form_classes(), False)
        return self._extra_forms

    def get_formsets(self):
        if not hasattr(self, '_formsets'):
            self._formsets = self._get_forms(self.get_formset_classes(), True)
        return self._formsets

    def get_context_data(self, *args, **kwargs):
        context = super(MultiFormMixin, self).get_context_data(*args, **kwargs)
        formsets = self.get_formsets()
        extra_forms = self.get_extra_forms()
        context.update({
            'extra_forms': extra_forms,
            'formsets': formsets,
        })
        return context

    def post(self, request, *args, **kwargs):
        try:
            self.object = self.get_object()
        except AttributeError:
            self.object = None
        form_class = self.get_form_class()
        form = self.get_form(form_class)
        if form.is_valid() and self.extra_forms_is_valid() and self.formsets_is_valid():
            next = self.form_valid(form)
            self.extra_forms_valid(self.object)
            self.formsets_valid(self.object)
            return next
        else:
            return self.form_invalid(form)

    def form_valid(self, form):
        self.object = form.save()
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        return self.render_to_response(self.get_context_data(form=form))

    def extra_forms_is_valid(self):
        extra_forms = self.get_extra_forms()
        # Do not return immediately when a form is invalid.
        # We want all forms cleaned.
        all_valid = True
        for form in extra_forms:
            if not form.is_valid():
                all_valid = False
        return all_valid

    def extra_forms_valid(self, object):
        extra_forms = self.get_extra_forms()
        for form in extra_forms:
            if hasattr(form, 'save') and hasattr(form.save, '__call__'):
                extra_obj = form.save(commit=False)
                if 'foreign_key_field' not in form.settings and 'field_name_for_object' not in form.settings:
                    raise ImproperlyConfigured('Extra form `%s` has no `foreign_key_field` defined.' % form)
                try:
                    setattr(extra_obj, form.settings.get('foreign_key_field', form.settings.get('field_name_for_object', None)), object)
                except:
                    pass
                extra_obj.save()
                if hasattr(form, 'save_m2m'):
                    form.save_m2m()

    def formsets_is_valid(self):
        formsets = self.get_formsets()
        # Do not return immediately when a form is invalid.
        # We want all formsets cleaned.
        all_valid = True
        for formset in formsets:
            if not formset.is_valid():
                all_valid = False
        return all_valid

    def formsets_valid(self, object):
        formsets = self.get_formsets()
        for formset in formsets:
            formset.instance = object
            formset.save()


class BetterListView(ListView):
    """
    A list view that supports:
     - Queryset actions
     - Single actions
     - Searching

    Defining queryset actions
    =========================

    Queryset actions can be defined by either defining the `actions` attribute or the `get_actions` method.
    The attribute, or the return value of the method, should be a sequence of 2-tuples (or 2-lists),
    in this format.

        (field_name_or_function, action_label)

    `field_name_or_function` can either be the name of a field of the model, or a function that
    accepts a queryset and returns an HttpResponse.

    Defining single actions
    =======================

    Single actions act on a single instance of the model. Single actions can be defined either by defining
    the `single_actions` attribute or the `get_single_actions` method. The attribute, or the return value
    of the method, should be a sequence of 2-tuples (or 2-lists), in this format:

        (field_name_or_function, action_label)

    `field_name_or_function` can either be the name of a field of the model, or a function that returns
    a function that accepts the single instance as its lone argument and returns a URL.

    Defining search fields
    ======================

    Search can be enabled by defining the `search_fields` attribute or the `get_search_fields` method.
    The attribute, or the return value of the method, must be a sequence of field names that will be
    used for looking up the query.

    Template requirements
    =====================

    The template receives the list of table columns, several URLs for creating, deleting, viewing and
    editing instances of the model, and the list of actions and search fields.

    An example of rendering queryset actions is as follows:

    <form method="POST" action="">{% csrf_token %}
        {% if actions %}
            <select name="action">
                <option value="">{% trans "(Select an action)" %}</option>
                {% for action in actions %}
                    <option value="{{ action.0 }}">{{ action.1|capfirst }}</option>
                {% endfor %}
            </select>
            <input type="submit" value="{% trans "Apply action" %}">
        {% endif %}
    </form>

    To render the search field:

    <form class="form-search" action="" method="GET">
        <input type="text" name="q" value="{% if search_query %}{{ search_query }}{% else %}{{ q }}{% endif %}">
        <button type="submit" class="btn"><i class="icon-search"></i></button>
    </form>

    Below is an example of rendering the table. This depends on a set of template tags whose implementation
    will be in another gist.

    <table>
        <thead>
            <tr>
                {# Script support for select all is left as an exercise to the reader. #}
                <th class="table-selection"><input type="checkbox" name="select_all" class="select-all" data-target="row-id"></th>
                {% for table_column in table_columns %}
                    <th>{{ table_column.1|title }}
                {% endfor %}
                <th class="list-actions">&nbsp;</th>
            </tr>
        </thead>
        <tbody>
            {% for object in object_list %}
                <tr>
                    <td>
                        <input type="checkbox" name="id" value="{{ object.pk }}" class="row-id">
                    </td>
                    {% for table_column in table_columns %}
                        <td>{% spaceless %}
                            {% if forloop.first %}
                                <a href="{{ object|call_on_object:detail_url }}">
                            {% endif %}
                            {% if object|get_table_column:table_column == 0%}
                                {{ object|get_table_column:table_column}}
                            {% else %}
                                {{ object|get_table_column:table_column|default:"None" }}
                            {% endif %}
                            {% if forloop.first %}
                                </a>
                            {% endif %}
                        {% endspaceless %}</td>
                    {% endfor %}
                    <td>
                        <ul>
                            {% if single_actions %}
                                {% for action in single_actions %}
                                    {% if action.2 and object|call_on_object:action.2 or not action.2 %}
                                        <li><a href="{{ object|call_on_object:action.0 }}">{{ action.1|title }}</a></li>
                                    {% endif %}
                                {% endfor %}
                            {% endif %}
                            <li><a href="{{ object|call_on_object:edit_url }}">{% trans "Edit" %}</a></li>
                            <li><a href="{{ object|call_on_object:delete_url }}">{% trans "Delete" %}</a></li>
                        </ul>
                    </td/>
                </tr>
            {% endfor %}
        </tbody>
    </table>

    """
    table_columns = (
        ('__unicode__', _('Name')),
    )
    actions = ()
    single_actions = ()
    search_fields = ()
    prefix = 'items'

    def get_queryset(self, *args, **kwargs):
        queryset = super(BetterListView, self).get_queryset(*args, **kwargs)
        q = self.request.GET.get('q', '')
        if q:
            filters = Q()
            for field in self.search_fields:
                filters = filters | Q(**{'%s__icontains' % field: q})
            queryset = queryset.filter(filters)
        return queryset

    def get_context_data(self, *args, **kwargs):
        context = super(BetterListView, self).get_context_data(*args, **kwargs)

        # Define default actions here because we need `self`.
        default_actions = (
            ('delete_selected', _('Delete the currently selected %(verbose_name_plural)s.') % {
                'verbose_name_plural': self.model._meta.verbose_name_plural
            }),
        )

        search_query = self.request.GET.get('q', '')

        extra_context = {
            'table_columns': self.get_table_columns(),
            'create_url': self.create_url,
            'edit_url': self.edit_url,
            'delete_url': self.delete_url,
            'detail_url': self.detail_url,
            'actions': self.get_actions() + default_actions,
            'single_actions': self.get_single_actions(),
            'has_search_enabled': bool(self.get_search_fields()),
            'search_query': search_query
        }
        context.update(extra_context)
        return context

    def post(self, *args, **kwargs):
        if not self.read_only:
            selected_action = self.request.POST.get('action', '')
            ids = self.request.POST.getlist('id')
            queryset = self.model.objects.filter(pk__in=ids)
            if selected_action:
                return self.process_action(selected_action, queryset)
        return redirect('%s_index' % self.get_prefix())

    def get_prefix(self):
        return self.prefix

    def get_table_columns(self):
        return self.table_columns

    def get_actions(self):
        return self.actions

    def get_single_actions(self):
        return self.single_actions

    def get_search_fields(self):
        return self.search_fields

    def process_action(self, action, queryset):
        if not self.read_only:
            return getattr(self, action)(queryset)
        return redirect('%s_index' % self.prefix)

    def delete_selected(self, queryset):
        queryset.delete()
        return redirect('%s_index' % self.prefix)

    def create_url(self):
        return reverse('%s_create' % self.prefix)

    def detail_url(self):
        return lambda o: o.get_absolute_url()

    def edit_url(self):
        return lambda o: reverse('%s_edit' % self.prefix, kwargs={'pk': o.pk})

    def delete_url(self):
        return lambda o: reverse('%s_delete' % self.prefix, kwargs={'pk': o.pk})
