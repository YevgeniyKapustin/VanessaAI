from wikipedia import PageError, DisambiguationError


def wiki_exception_handler(func):

    def wrapper(self):
        from wikipedia import WikipediaException
        try:
            return func(self)
        except PageError:
            return self._handling_page_error()
        except DisambiguationError as error:
            return self._handling_disambiguation(error)
        except WikipediaException:
            return self._handling_wiki_exception()

    return wrapper
