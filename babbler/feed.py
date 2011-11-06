
import logging
from math import ceil
from time import sleep, time

from feedparser import parse


class Feed(object):
    """
    Generator that requests entries for an RSS feed, returning each
    while pausing between each entry returned.
    """

    def __init__(self):
        self.todo = []
        self.done = set()

    def setup(self, options):
        """
        Set up options.
        """
        self.feed_url = options["feed_url"]
        self.pause = options["pause"]
        self.queue_slice = options["queue_slice"]
        self.max_len = options["max_len"]
        self.ignore = options["ignore"]

    def saved(self):
        return set([t["id"] for t in self.todo]) | self.done

    def entries(self):
        """
        Loads the RSS feed in reverse order and return new entries.
        """
        entries = []
        feed = parse(self.feed_url)
        try:
            error = str(feed["bozo_exception"]).strip()
        except KeyError:
            pass
        else:
            logging.error("Feed error: %s" % error)
        saved = self.saved()
        for entry in reversed(feed.entries):
            if entry["id"] not in saved:
                # Ignore entries that match any ignore string, are too
                # long, or are already in "todo" or "done".
                ignored = []
                if self.ignore:
                    ignored = [s for s in self.ignore.split(",")
                               if s and s.lower() in entry["title"].lower()]
                if ignored:
                    logging.debug("Ignore strings (%s) found in: %s" %
                                  (", ".join(ignored), entry["title"]))
                    self.done.add(entry["id"])
                elif len(entry["title"]) > self.max_len:
                    logging.debug("Entry too long: %s" % entry["title"])
                    self.done.add(entry["id"])
                else:
                    entry = {"id": entry["id"], "title": entry["title"]}
                    entries.append(entry)
        return entries

    def __iter__(self):
        """
        Moves any new entries onto the "todo" queue and yields the first
        entry in the "todo" queue. Regardless of new entries, pause on
        each iteration, taking the queue_slice setting into account.
        """
        last_feed_time = 0
        while True:
            # Get new entries and save the data file if new entries found
            # if the pause period has elapsed.
            if ((last_feed_time + self.pause) - time()) <= 0:
                last_feed_time = time()
                entries = self.entries()
                logging.debug("New queued entries: %s" % len(entries))
                if entries:
                    self.todo.extend(entries)
                # Update the time to sleep - use the pause option unless
                # there are items in the "todo" queue, otherwise set the
                # pause to consume the portion of the queue size defined
                # by the queue_slice option before the next feed request.
                pause = self.pause
                if len(self.todo) > self.queue_slice * 10:
                    queue_slice = ceil(len(self.todo) * self.queue_slice)
                    pause = int(pause / queue_slice)
            # Yield the first entry in the "todo" list.
            if self.todo:
                logging.debug("Total queued entries: %s" % len(self.todo))
                yield self.todo[0]
            logging.debug("Pausing for %s seconds" % pause)
            sleep(pause)

    def process(self):
        """
        Move the first entry in the "todo" queue to the "done" set.
        """
        self.done.add(self.todo.pop(0)["id"])
