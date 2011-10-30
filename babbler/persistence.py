
from cPickle import dump, load
from os import remove


class PersistentDict(dict):
    """
    Dictionary that persists itself to a pickle file.
    """

    def __init__(self, path):
        self.path = path

    def load(self):
        """
        Load self from file.
        """
        try:
            with open(self.path, "rb") as f:
                self.update(load(f))
                return True
        except IOError:
            return False

    def save(self):
        """
        Save self to file.
        """
        with open(self.path, "wb") as f:
            dump(self, f)

    def remove(self):
        """
        Remove file.
        """
        remove(self.path)
