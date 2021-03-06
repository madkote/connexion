# Decorators to split query and path parameters
import abc
import functools
import logging

import six

from .decorator import BaseDecorator

logger = logging.getLogger('connexion.decorators.uri_parsing')


@six.add_metaclass(abc.ABCMeta)
class AbstractURIParser(BaseDecorator):
    def __init__(self, param_defns):
        """
        a URI parser is initialized with parameter definitions.
        When called with a request object, it handles array types in the URI
        both in the path and query according to the spec.
        Some examples include:
         - https://mysite.fake/in/path/1,2,3/            # path parameters
         - https://mysite.fake/?in_query=a,b,c           # simple query params
         - https://mysite.fake/?in_query=a|b|c           # various separators
         - https://mysite.fake/?in_query=a&in_query=b,c  # complex query params
        """
        self._param_defns = {p["name"]: p
                             for p in param_defns
                             if p["in"] in ["query", "path"]}

    @abc.abstractproperty
    def param_defns(self):
        """
        returns the parameter definitions by name
        """

    @abc.abstractproperty
    def param_schemas(self):
        """
        returns the parameter schemas by name
        """

    def __repr__(self):
        """
        :rtype: str
        """
        return "<{classname}>".format(classname=self.__class__.__name__)

    @abc.abstractmethod
    def _resolve_param_duplicates(self, values, param_defn):
        """ Resolve cases where query parameters are provided multiple times.
            For example, if the query string is '?a=1,2,3&a=4,5,6' the value of
            `a` could be "4,5,6", or "1,2,3" or "1,2,3,4,5,6" depending on the
            implementation.
        """

    @abc.abstractmethod
    def _split(self, value, param_defn):
        """
        takes a string, and a parameter definition, and returns
        an array that has been constructed according to the parameter
        definition.
        """

    def resolve_params(self, params, resolve_duplicates=False):
        """
        takes a dict of parameters, and resolves the values into
        the correct array type handling duplicate values, and splitting
        based on the collectionFormat defined in the spec.
        """
        resolved_param = {}
        for k, values in params.items():
            param_defn = self.param_defns.get(k)
            param_schema = self.param_schemas.get(k)
            if not (param_defn or param_schema):
                # rely on validation
                resolved_param[k] = values
                continue

            if not resolve_duplicates:
                values = [values]

            if (param_schema is not None and param_schema['type'] == 'array'):
                # resolve variable re-assignment, handle explode
                values = self._resolve_param_duplicates(values, param_defn)
                # handle array styles
                resolved_param[k] = self._split(values, param_defn)
            else:
                resolved_param[k] = values[-1]

        return resolved_param

    def __call__(self, function):
        """
        :type function: types.FunctionType
        :rtype: types.FunctionType
        """

        @functools.wraps(function)
        def wrapper(request):

            try:
                query = request.query.to_dict(flat=False)
            except AttributeError:
                query = dict(request.query.items())

            try:
                path_params = request.path_params.to_dict(flat=False)
            except AttributeError:
                path_params = dict(request.path_params.items())

            request.query = self.resolve_params(query, resolve_duplicates=True)
            request.path_params = self.resolve_params(path_params)
            response = function(request)
            return response

        return wrapper


class Swagger2URIParser(AbstractURIParser):
    """
    Adheres to the Swagger2 spec,
    Assumes the the last defined query parameter should be used.
    """

    @property
    def param_defns(self):
        return self._param_defns

    @property
    def param_schemas(self):
        return self._param_defns  # swagger2 conflates defn and schema

    @staticmethod
    def _resolve_param_duplicates(values, param_defn):
        """ Resolve cases where query parameters are provided multiple times.
            The default behavior is to use the first-defined value.
            For example, if the query string is '?a=1,2,3&a=4,5,6' the value of
            `a` would be "4,5,6".
            However, if 'collectionFormat' is 'multi' then the duplicate values
            are concatenated together and `a` would be "1,2,3,4,5,6".
        """
        if param_defn.get('collectionFormat') == 'multi':
            return ','.join(values)
        # default to last defined value
        return values[-1]

    @staticmethod
    def _split(value, param_defn):
        if param_defn.get("collectionFormat") == 'pipes':
            return value.split('|')
        return value.split(',')


class FirstValueURIParser(Swagger2URIParser):
    """
    Adheres to the Swagger2 spec
    Assumes that the first defined query parameter should be used
    """

    @staticmethod
    def _resolve_param_duplicates(values, param_defn):
        """ Resolve cases where query parameters are provided multiple times.
            The default behavior is to use the first-defined value.
            For example, if the query string is '?a=1,2,3&a=4,5,6' the value of
            `a` would be "1,2,3".
            However, if 'collectionFormat' is 'multi' then the duplicate values
            are concatenated together and `a` would be "1,2,3,4,5,6".
        """
        if param_defn.get('collectionFormat') == 'multi':
            return ','.join(values)
        # default to first defined value
        return values[0]


class AlwaysMultiURIParser(Swagger2URIParser):
    """
    Does not adhere to the Swagger2 spec, but is backwards compatible with
    connexion behavior in version 1.4.2
    """

    @staticmethod
    def _resolve_param_duplicates(values, param_defn):
        """ Resolve cases where query parameters are provided multiple times.
            The default behavior is to join all provided parameters together.
            For example, if the query string is '?a=1,2,3&a=4,5,6' the value of
            `a` would be "1,2,3,4,5,6".
        """
        if param_defn.get('collectionFormat') == 'pipes':
            return '|'.join(values)
        return ','.join(values)
