import importlib
import logging

import facepy
from facepy.exceptions import FacebookError

from django.conf import settings


def get_class(class_name):
    module_name, class_name = class_name.rsplit(".", 1)

    module = importlib.import_module(module_name)
    return getattr(module, class_name)

FACEBOOK_GRAPH_OBSERVERS = getattr(settings, 'FACEBOOK_GRAPH_OBSERVERS', [])
GRAPH_OBSERVER_CLASSES = map(get_class, FACEBOOK_GRAPH_OBSERVERS)


logger = logging.getLogger(__name__)


class ObservableGraphAPI(facepy.GraphAPI):
    def __init__(self, *args, **kwargs):
        super(ObservableGraphAPI, self).__init__(*args, **kwargs)
        self.session = ObservableSession(self.session)

    def _query(self, *args, **kwargs):
        handlers = FacebookConnectionObservers()
        self.session.observers.append(handlers)
        try:
            response = super(ObservableGraphAPI, self)._query(*args, **kwargs)
        except FacebookError as e:
            handlers.handle_error(e)
            raise
        finally:
            self.session.observers.remove(handlers)
            handlers.finalize()
        return response

    def batch(self, requests):
        logger.warn('Errors of batch method are not watched')
        return super(ObservableGraphAPI, self).batch(requests)


class ObservableSession(object):
    def __init__(self, other_session):
        self.other_session = other_session
        self.observers = []

    def request(self, *args, **kwargs):
        self.notify_request(*args, **kwargs)
        response = self.other_session.request(*args, **kwargs)
        self.notify_response(response)
        return response

    def notify_request(self, *args, **kwargs):
        for observer in self.observers:
            observer.handle_request(*args, **kwargs)

    def notify_response(self, response):
        for observer in self.observers:
            observer.handle_response(response)


class FacebookConnectionObservers(object):
    def __init__(self):
        self.request = None
        self.response = None
        self.error = None

    def handle_request(self, *args, **kwargs):
        self.request = RequestInfo(*args, **kwargs)

    def handle_response(self, response):
        self.response = response

    def handle_error(self, error):
        self.error = error

    def finalize(self):
        for observer_class in GRAPH_OBSERVER_CLASSES:
            observer = observer_class()
            observer.handle_facebook_communication(
                self.request, self.response, self.error)


class RequestInfo(object):
    def __init__(self, url, method, **kwargs):
        self.url = url
        self.method = method
        self.kwargs = kwargs
