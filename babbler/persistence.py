
from cPickle import dump, load


class PersistentDict(dict):
    """
    Dictionary persisted to a pickle file.
    """

    def __init__(self, path):
        self.path = path

    def load(self):
        try:
            with open(self.path, "rb") as f:
                self.update(load(f))
                return True
        except IOError:
            return False

    def save(self):
        with open(self.path, "wb") as f:
            dump(self, f)
