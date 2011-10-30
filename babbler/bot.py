#!/usr/bin/env python

from code import interact
import logging
from os import getcwd, kill
from os.path import dirname, join
import sys; sys.path.insert(0, getcwd())

from daemon import daemonize
from twitter import Api, TwitterError

from babbler.feed import Feed
from babbler.options import Options
from babbler.tagging import Tagger
from babbler.persistence import PersistentDict


DATA_PATH = join(getcwd(), "babbler.data")
PID_PATH = join(getcwd(), "babbler.pid")
LOG_PATH = join(getcwd(), "babbler.log")
OPTIONS_PATH = join(dirname(__file__), "options.yml")
TWEET_MAX_LEN = 140


def configure_and_load():
    """
    Handles command-line arg parsing and loading of data.
    """
    data = PersistentDict(path=DATA_PATH)
    existing_options = {}
    if data.load():
        existing_options = data["options"]
        # Migrate from 0.1 format.
        if "todo" in data:
            data["feed"] = Feed()
            data["feed"].todo = data.pop("todo")
            data["feed"].done = data.pop("done")
    else:
        print
        print "Initial setup. Data will be saved to '%s'" % DATA_PATH
        print
    from __init__ import __doc__, __version__
    options = Options(OPTIONS_PATH, existing=existing_options,
                      description=__doc__.strip(), __version__=version)
    data["options"] = options.parse_args()
    data.save()
    return data


def destroy(data, api):
    """
    Destroys persisted data file and deletes all tweets from Twitter
    when the --DESTROY option is given.
    """
    print
    print "WARNING: You have specified the --DESTROY option."
    print "All tweets will be deleted from your account."
    if raw_input("Enter 'y' to continue. ").strip().lower() == "y":
        print "Deleting all data and tweets."
        try:
            data.remove()
        except OSError:
            pass
        while True:
            tweets = api.GetUserTimeline()
            if not tweets:
                break
            for tweet in tweets:
                try:
                    api.DestroyStatus(tweet.id)
                except TwitterError:
                    pass
        print "Done."
    else:
        print "--DESTROY aborted"


def edit(data, api):
    """
    Runs a Python shell for editing the data file.
    """
    print
    print "All data is stored in the persisted dictionary named 'data' "
    print "which contains the follwing entries:"
    print
    print "data['feed'].done = set()  # All entry IDs that have either been "
    print "                           # posted to Twitter, or ignored. "
    print "data['feed'].todo = []     # All entries that have been retrieved "
    print "                           # from the feed and are waiting to be "
    print "                           # posted to Twitter. Each dict contains "
    print "                           # 'id' and 'title' keys."
    print "data['options'] = {}       # All options that have been persisted. "
    print
    print "The 'data.save()' method can be called to persist changes made."
    print
    local = locals()
    local.update(globals())
    interact(local=local)


def run(data, api):
    """
    Main event loop that gets the entries from the feed and posts them
    to Twitter.
    """

    # Set up the feed.
    data.setdefault("feed", Feed())
    data["feed"].setup(dict(max_len=TWEET_MAX_LEN, **data["options"]))
    data.save()

    # Set up logging.
    kwargs = {"format": "%(asctime)-15s %(levelname)-5s %(message)s"}
    if data["options"]["daemonize"]:
        kwargs.update({"filename": LOG_PATH, "filemode": "wb"})
    logging.basicConfig(**kwargs)
    log_level = getattr(logging, data["options"]["log_level"])
    logging.getLogger().setLevel(log_level)

    # Set up hashtagging.
    def hashtag_score(hashtag):
        try:
            results = api.GetSearch("#" + hashtag)
        except TwitterError, e:
            logging.error("Twitter error: %s" % e)
        except UnicodeEncodeError:
            pass
        else:
            return sum([t.created_at_in_seconds for t in results])
        return 0
    hashtag_min_length = data["options"]["hashtag_min_length"]
    tagger = Tagger(scorer=hashtag_score, min_length=hashtag_min_length)

    # Main loop.
    logging.debug("\n\nUsing options:\n\n%s\n" % data["options"])
    for entry in data["feed"]:
        for tag in tagger.tags(entry):
            tag = " #" + tag
            if len(entry + tag) <= TWEET_MAX_LEN:
                entry += tag
        # Post to Twitter.
        done = True
        try:
            if not data["options"]["dry_run"]:
                api.PostUpdate(entry)
        except TwitterError, e:
            logging.error("Twitter error: %s" % e)
            # Mark the entry as done if it's a duplicate.
            done = str(e) == "Status is a duplicate."
        if done:
            logging.info("Tweeted: %s" % entry)
            # Move the entry from "todo" to "done" and save.
            data["feed"].process()
            if not data["options"]["dry_run"]:
                data.save()

def kill_daemon():
    """
    Try to stop a previously started daemon.
    """
    try:
        with open(PID_PATH) as f:
            kill(int(f.read()), 9)
        remove(PID_PATH)
    except (IOError, OSError):
        return False
    return True


def main():
    """
    Main entry point for the program.
    """

    # Configure and load data.
    data = configure_and_load()

    # Set up the Twitter API object.
    api = Api(**dict([(k, v) for k, v in data["options"].items()
                      if k.split("_")[0] in ("consumer", "access")]))

    if data["options"]["destroy"]:
        # Reset all data and delete tweets if specified.
        destroy(data, api)
    elif data["options"]["kill"]:
        # Kill a previously started daemon.
        if kill_daemon():
            print "Daemon killed"
        else:
            print "Couldn't kill daemon"
    elif data["options"]["edit_data"]:
        # Run a Python shell for editing data.
        edit(data, api)
    elif data["options"]["daemonize"]:
        # Start a new daemon.
        kill_daemon()
        daemonize(PID_PATH)
        run(data, api)
        print "Daemon started"
    else:
        # Start in the foreground.
        try:
            run(data, api)
        except KeyboardInterrupt:
            print
            print "Quitting"


if __name__ == "__main__":
    main()
