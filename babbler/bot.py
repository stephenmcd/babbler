#!/usr/bin/env python

from code import interact
import logging
from os import getcwd, kill, remove
from os.path import join
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
TWEET_MAX_LEN = 140


def configure_and_load():
    """
    Handles command-line arg parsing and loading of data.
    """

    # Maintain defaults separately, since OptionParser doesn't provide
    # a way of distinguishing between an option provided or a default
    # used.
    defaults = {
        "ignore": [],
        "hashtag_min_length": 3,
        "pause": 600,
        "log_level": "INFO",
        "queue_slice": 0.3,
    }

    # Options that can have their provided values appended to their
    # persisted values when the --append switch is used.
    appendable = ("--ignore", "--hashtag-min-length", "--pause",
                  "--queue-slice")

    data = PersistentDict(path=DATA_PATH)
    if data.load():
        defaults.update(data["options"])
        # Migrate from 0.1 format.
        if "todo" in data:
            data["feed"] = Feed()
            data["feed"].todo = data.pop("todo")
            data["feed"].done = data.pop("done")
    else:
        print
        print "Initial setup. Data will be saved to '%s'" % DATA_PATH
        print

    from __init__ import __doc__ as doc, __version__ as version
    options = Options(usage="usage: %prog [options]", description=doc.strip(),
                      version=version, defaults=defaults, appendable=appendable,
                      append_option="append", subtract_option="subtract",
                      epilog="Options need only be provided once via command "
                             "line as options specified are then persisted in "
                             "the data file, and reused on subsequent runs. "
                             "Required options can also be omitted as they "
                             "will each then be prompted for individually.")

    with options.group("Required") as g:
        g.add_option("-u", "--feed-url",
                     dest="feed_url", metavar="url",
                     help="RSS Feed URL")

    with options.group("Optional") as g:
        g.add_option("-i", "--ignore",
                     dest="ignore", metavar="strings",
                     help="Comma separated strings for ignoring feed entries "
                          "if they contain any of the strings")
        g.add_option("-p", "--pause", type="int",
                     dest="pause", metavar="seconds",
                     help="Seconds between RSS feed requests (default:%s) " %
                          defaults["pause"])
        g.add_option("-q", "--queue-slice", type="float",
                     dest="queue_slice", metavar="decimal",
                     help="Decimal fraction of unposted tweets to send during "
                          "each iteration between feed requests (default:%s) " %
                          defaults["queue_slice"])
        log_levels = ("ERROR", "INFO", "DEBUG")
        g.add_option("-l", "--log-level", choices=log_levels,
                     dest="log_level", metavar="level",
                     help="Level of information printed (%s) (default:%s)" %
                          ("|".join(log_levels), defaults["log_level"]))
        g.add_option("-m", "--hashtag-min-length", type="int",
                     dest="hashtag_min_length", metavar="len",
                     help="Minimum length of a hashtag (default:%s)" %
                          defaults["hashtag_min_length"])

    with options.group("Switches") as g:
        g.add_option("-a", "--append",
                     dest="append", action="store_true", default=False,
                     help="Switch certain options into append mode where their "
                          "values provided are appended to their persisted "
                          "values, namely %s" % ", ".join(appendable))
        g.add_option("-s", "--subtract",
                     dest="subtract", action="store_true", default=False,
                     help="Opposite of --append")
        g.add_option("-e", "--edit-data",
                     dest="edit_data", action="store_true", default=False,
                     help="Load a Python shell for editing the data file")
        g.add_option("-f", "--dry-run",
                     dest="dry_run", action="store_true", default=False,
                     help="Fake run that doesn't save data or post tweets")
        g.add_option("-d", "--daemonize",
                     dest="daemonize", action="store_true", default=False,
                     help="Run as a daemon")
        g.add_option("-k", "--kill",
                     dest="kill", action="store_true", default=False,
                     help="Kill a previously started daemon")
        g.add_option("-D", "--DESTROY",
                     dest="destroy", action="store_true", default=False,
                     help="Deletes all saved data and tweets from Twitter")

    with options.group("Twitter authentication (all required)") as g:
        g.add_option("-w", "--consumer-key",
                     dest="consumer_key", metavar="key",
                     help="Twitter Consumer Key")
        g.add_option("-x", "--consumer-secret",
                     dest="consumer_secret", metavar="secret",
                     help="Twitter Consumer Secret")
        g.add_option("-y", "--access-token-key",
                     dest="access_token_key", metavar="key",
                     help="Twitter Access Token Key")
        g.add_option("-z", "--access-token-secret",
                     dest="access_token_secret", metavar="secret",
                     help="Twitter Access Token Secret")

    data["options"] = options.parse_args()
    data.save()
    return data


def destroy(api):
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
            remove(DATA_PATH)
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


def edit():
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
    interact(local=globals())


def run(data, api):
    """
    Main event loop that gets the entries from the feed and posts them
    to Twitter.
    """
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

    logging.debug("\n\nUsing options:\n\n%s\n" % data["options"])

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
        destroy(api)
    elif data["options"]["kill"]:
        # Kill a previously started daemon.
        if kill_daemon():
            print "Daemon killed"
        else:
            print "Couldn't kill daemon"
    elif data["options"]["edit_data"]:
        # Run a Python shell for editing data.
        edit()
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
