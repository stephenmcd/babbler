#!/usr/bin/env python

"""
A Twitter bot that polls an RSS feed and posts the feed's titles as
tweets, extracting words from the titles to use as hashtags.
"""

from __future__ import with_statement
from code import interact
from cPickle import dump, load
import logging
from math import ceil
from optparse import OptionGroup, OptionParser
from os import getcwd, kill, remove
from os.path import dirname, join
from time import sleep, time


__version__ = "0.1.3"


DATA_PATH = join(getcwd(), "babbler.data")
PID_PATH = join(getcwd(), "babbler.pid")
LOG_PATH = join(getcwd(), "babbler.log")
TWEET_MAX_LEN = 140


def wordfile(filename):
    """
    Returns a set word list from a file.
    Used for dictionary and stopwords.
    """
    with open(join(dirname(__file__), "wordfiles", filename)) as f:
        return set([s.strip() for s in f])


def save(dry_run=False):
    """
    Persists the data file to disk.
    """
    if not dry_run:
        with open(DATA_PATH, "wb") as f:
            dump(data, f)


def configure_and_load():
    """
    Handles command-line arg parsing and loading of options and data.
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

    parser = OptionParser(usage="usage: %prog [options]",
                          description=__doc__.strip(), version=__version__,
                          epilog="Options need only be provided once via "
                                 "command line as options specified are then "
                                 "persisted in the data file, and reused "
                                 "on subsequent runs. Required options can "
                                 "also be omitted as they will each then be "
                                 "prompted for individually.")

    group = OptionGroup(parser, "Required")
    group.add_option("-u", "--feed-url",
                     dest="feed_url", metavar="url",
                     help="RSS Feed URL")
    parser.add_option_group(group)

    group = OptionGroup(parser, "Optional")
    group.add_option("-i", "--ignore",
                     dest="ignore", metavar="strings",
                     help="Comma separated strings for ignoring feed entries "
                          "if they contain any of the strings")
    group.add_option("-p", "--pause", type="int",
                     dest="pause", metavar="seconds",
                     help="Seconds between RSS feed requests "
                          "(default:%s) " % defaults["pause"])
    group.add_option("-q", "--queue-slice", type="float",
                     dest="queue_slice", metavar="decimal",
                     help="Decimal fraction of unposted tweets to send "
                          "during each iteration between feed requests "
                          "(default:%s) " % defaults["queue_slice"])
    log_levels = ("ERROR", "INFO", "DEBUG")
    group.add_option("-l", "--log-level", choices=log_levels,
                     dest="log_level", metavar="level",
                     help="Level of information printed (%s) "
                          "(default:%s)" % ("|".join(log_levels),
                                             defaults["log_level"]))
    group.add_option("-m", "--hashtag-min-length", type="int",
                     dest="hashtag_min_length", metavar="len",
                     help="Minimum length of a hashtag "
                          "(default:%s)" % defaults["hashtag_min_length"])
    parser.add_option_group(group)

    group = OptionGroup(parser, "Switches")
    group.add_option("-a", "--append",
                     dest="append", action="store_true", default=False,
                     help="Switch certain options into append mode where "
                          "their values provided are appended to their "
                          "persisted values, namely %s" % ", ".join(appendable))
    group.add_option("-s", "--subtract",
                     dest="subtract", action="store_true", default=False,
                     help="Opposite of --append")
    group.add_option("-e", "--edit-data",
                     dest="edit_data", action="store_true", default=False,
                     help="Load a Python shell for editing the data file")
    group.add_option("-f", "--dry-run",
                     dest="dry_run", action="store_true", default=False,
                     help="Fake run that doesn't save data or post tweets")
    group.add_option("-d", "--daemonize",
                     dest="daemonize", action="store_true", default=False,
                     help="Run as a daemon")
    group.add_option("-k", "--kill",
                     dest="kill", action="store_true", default=False,
                     help="Kill a previously started daemon")
    group.add_option("-D", "--DESTROY",
                     dest="destroy", action="store_true", default=False,
                     help="Deletes all saved data and tweets from Twitter")
    parser.add_option_group(group)

    group = OptionGroup(parser, "Twitter authentication (all required)")
    group.add_option("-w", "--consumer-key",
                     dest="consumer_key", metavar="key",
                     help="Twitter Consumer Key")
    group.add_option("-x", "--consumer-secret",
                     dest="consumer_secret", metavar="secret",
                     help="Twitter Consumer Secret")
    group.add_option("-y", "--access-token-key",
                     dest="access_token_key", metavar="key",
                     help="Twitter Access Token Key")
    group.add_option("-z", "--access-token-secret",
                     dest="access_token_secret", metavar="secret",
                     help="Twitter Access Token Secret")
    parser.add_option_group(group)

    (parsed_options, _) = parser.parse_args()

    try:
        # Try and load a previously saved data file.
        with open(DATA_PATH, "rb") as f:
            data = load(f)
    except IOError:
        # Create the default data file.
        print
        print "Initial setup. Data will be saved to '%s'" % DATA_PATH
        print
        data = {"options": {}, "todo": [], "done": set()}
    options = [o for g in parser.option_groups for o in g.option_list]
    for option in options:
        name = option.dest
        if name is not None:
            value = getattr(parsed_options, name)
            default = data["options"].get(name, defaults.get(name))
            if value is not None and option.get_opt_string() in appendable:
                if parsed_options.append:
                    if option.type == "string" and not value.startswith(","):
                        value = "," + value
                    value = default + value
                elif parsed_options.subtract:
                    if option.type == "string" and not value.startswith(","):
                        default = set(default.split(","))
                        value = set(value.split(","))
                        value = ",".join(default - value)
                    else:
                        value = default - value
            if value is None:
                value = default
            if value is None:
                value = raw_input("Please enter '%s': " % option.help)
            data["options"][name] = value

    # Set up logging.
    kwargs = {"format": "%(asctime)-15s %(levelname)-5s %(message)s"}
    if data["options"]["daemonize"]:
        kwargs.update({"filename": LOG_PATH, "filemode": "wb"})
    logging.basicConfig(**kwargs)
    log_level = getattr(logging, data["options"]["log_level"])
    logging.getLogger().setLevel(log_level)

    formatted_options = []
    padding = len(max(data["options"].keys(), key=len)) + 5
    for option in options:
        name = (option.dest + ": ").ljust(padding, ".")
        value = data["options"][option.dest]
        formatted_options.append("%s %s" % (name, value))
    logging.debug("\n\nUsing options:\n\n%s\n" % "\n".join(formatted_options))

    return data


def destroy():
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
    print "All data is stored in the dictionary named 'data' "
    print "which contains the follwing entries:"
    print
    print "data['done'] = set()  # All entry IDs that have either been "
    print "                      # posted to Twitter, or ignored. "
    print "data['todo'] = []     # All entries that have been retrieved "
    print "                      # from the feed and are waiting to be "
    print "                      # posted to Twitter. Each dict contains "
    print "                      # 'id' and 'title' keys."
    print "data['options'] = {}  # All options that have been persisted. "
    print
    print "The 'save()' function can be called to persist any changes made."
    print
    interact(local=globals())


def get_new_entries():
    """
    Loads the RSS feed in reverse order and return new entries.
    """
    from feedparser import parse
    entries = []
    feed = parse(options["feed_url"])
    try:
        logging.error("Feed error: %s" % str(feed["bozo_exception"]).strip())
    except KeyError:
        pass
    saved = set([t["id"] for t in data["todo"]]) | data["done"]
    for entry in reversed(feed.entries):
        if entry["id"] not in saved:
            # Ignore entries that match any ignore string, can't fit
            # into a tweet, or are already in "todo" or "done".
            ignored = []
            if options["ignore"]:
                ignored = [s for s in options["ignore"].split(",")
                           if s and s.lower() in entry["title"].lower()]
            if ignored:
                logging.debug("Ignore strings (%s) found in: %s" %
                              (", ".join(ignored), entry["title"]))
                data["done"].add(entry["id"])
            elif len(entry["title"]) > TWEET_MAX_LEN:
                logging.debug("Entry too long: %s" % entry["title"])
                data["done"].add(entry["id"])
            else:
                entries.append({"id": entry["id"], "title": entry["title"]})
    return entries


def possible_hashtags_for_index(words, i):
    """
    Returns up to 4 possible hashtags - all combinations of the next
    and previous words for the given index. If the word has a
    possessive apostrophe, use the singular form.
    """
    valid_prev = i > 0 and words[i - 1].lower() not in stopwords
    valid_next = i < len(words) - 1 and words[i + 1].lower() not in stopwords
    word = words[i] if not words[i].lower().endswith("'s") else words[i][:-2]
    possible_hashtags = [word]
    if valid_prev:
        # Combined with previous word.
        possible_hashtags.append(words[i - 1] + word)
    if valid_next:
        # Combined with next word.
        possible_hashtags.append(word + words[i + 1])
    if valid_prev and valid_next:
        # Combined with previous and next words.
        possible_hashtags.append(words[i - 1] + word + words[i + 1])
    # Remove apostophes.
    return [t.replace("'", "") for t in possible_hashtags]


def best_hashtag_with_score(possible_hashtags):
    """
    Given possible hashtags, calculates a score for each based on the
    time since epoch of each search result for the hashtag, and returns
    the highest scoring hashtag/score pair.
    """
    best_hashtag = None
    highest_score = 0
    for hashtag in possible_hashtags:
        if len(hashtag) >= options["hashtag_min_length"]:
            try:
                results = api.GetSearch("#" + unicode(hashtag).decode())
            except TwitterError, e:
                logging.error("Twitter error: %s" % e)
            except UnicodeEncodeError:
                pass
            else:
                score = sum([t.created_at_in_seconds for t in results])
                logging.debug("Score for '%s': %s" % (hashtag, score))
                if score > highest_score:
                    highest_score = score
                    best_hashtag = hashtag
    return best_hashtag, highest_score


def tweet_with_hashtags(tweet):
    """
    Parses hashtags from the given tweet and adds them to the
    returned tweet.

    Steps:

    1) Go through every word in the tweet and if non-dictionary and
       non-numeric, create up to 4 possible hashtags from it, the word
       combined with the previous word, the next word, both previous
       and next words together, and the word itself. Only use previous
       and next words that aren't stopwords.
    2) Ignore all the possible hashtags from the word if any of
       them have already been added as hashtags, eg via the previous
       or next word iteration, or a duplicate word.
    3) Search for the possible hashtags via the API, giving each a
       score based on the sum of the seconds since epoch for each
       search result, and pick the highest scoring hashtag to use from
       the possibilites for that word.
    4) Sort the chosen hashtags found for all words by score, and add
       as many as possible to the tweet within its length limit.
    """

    logging.debug("Getting hashtags for: %s" % tweet)
    # String for word list - treat dashes and slashes as separators.
    cleaned = tweet.replace("-", " ").replace("/", " ")
    # Initial list of alphanumeric words.
    words = "".join([c for c in cleaned if c.isalnum() or c in "' "]).split()
    # All hashtags mapped to scores.
    hashtags = {}
    for i, word in enumerate(words):
        word = word.replace("'", "")
        if not (word.isdigit() or word.lower() in dictionary):
            possible_hashtags = possible_hashtags_for_index(words, i)
            logging.debug("Possible hashtags for the word '%s': %s" %
                          (word, ", ".join(possible_hashtags)))
            # Check none of the possibilities have been used.
            used = [t.lower() for t in hashtags.keys()]
            if [t for t in possible_hashtags if t.lower() in used]:
                logging.debug("Possible hashtags already used")
            else:
                hashtag, score = best_hashtag_with_score(possible_hashtags)
                if hashtag is not None:
                    logging.debug("Best hashtag for the word '%s': %s" %
                                  (word, hashtag))
                    hashtags[hashtag] = score

    # Sort hashtags by score and add to tweet.
    hashtags = sorted(hashtags.keys(), key=lambda k: hashtags[k], reverse=True)
    logging.debug("Hashtags chosen: %s" % (", ".join(hashtags)
                                           if hashtags else "None"))
    for hashtag in hashtags:
        hashtag = " #" + hashtag
        if len(tweet + hashtag) <= TWEET_MAX_LEN:
            tweet += hashtag
    return tweet


def run(dry_run):
    """
    Main event loop that gets the entries from the feed and goes through
    them, oldest first, adding them to the "todo" queue. Then takes the
    first from the queue and posts it to Twitter. Finally pauses for the
    amount of time estimated to flush the "todo" queue by the time the
    feed is requested again.
    """
    last_feed_time = 0
    while True:
        # Get new entries and save the data file if new entries found
        # if the pause period has elapsed.
        if ((last_feed_time + options["pause"]) - time()) <= 0:
            last_feed_time = time()
            new_entries = get_new_entries()
            logging.debug("New queued entries: %s" % len(new_entries))
            if new_entries:
                data["todo"].extend(new_entries)
                save(dry_run=dry_run)
            # Update the time to sleep - use the pause option unless
            # there are items in the "todo" queue, otherwise set the
            # pause to consume the portion of the queue size defined
            # by the queue_slice option before the next feed request.
            pause = options["pause"]
            if len(data["todo"]) > options["queue_slice"] * 10:
                queue_slice = ceil(len(data["todo"]) * options["queue_slice"])
                pause = int(pause / queue_slice)
        # Process the first entry in the "todo" list.
        if data["todo"]:
            logging.debug("Total queued entries: %s" % len(data["todo"]))
            tweet = tweet_with_hashtags(data["todo"][0]["title"])
            # Post to Twitter.
            done = True
            try:
                if not dry_run:
                    api.PostUpdate(tweet)
            except TwitterError, e:
                logging.error("Twitter error: %s" % e)
                # Mark the entry as done if it's a duplicate.
                done = str(e) == "Status is a duplicate."
            if done:
                logging.info("Tweeted: %s" % tweet)
                # Move the entry from "todo" to "done" and save.
                data["done"].add(data["todo"].pop(0)["id"])
                save(dry_run=dry_run)
        logging.debug("Pausing for %s seconds" % pause)
        sleep(pause)


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
    Main entry point for program.
    """
    from daemon import daemonize
    from twitter import Api, TwitterError

    global data, options, api, dictionary, stopwords

    # Configure and load data.
    data = configure_and_load()
    save()
    options = data["options"]

    # Set up the Twitter API object.
    api = Api(**dict([(k, v) for k, v in options.items()
                      if k.split("_")[0] in ("consumer", "access")]))

    # Set up word files.
    dictionary = wordfile("dictionary.txt")
    stopwords = wordfile("stopwords.txt")

    if options["destroy"]:
        # Reset all data and delete tweets if specified.
        destroy()
    elif options["kill"]:
        # Kill a previously started daemon.
        if kill_daemon():
            print "Daemon killed"
        else:
            print "Couldn't kill daemon"
    elif options["edit_data"]:
        # Run a Python shell for editing data.
        edit()
    elif options["daemonize"]:
        # Start a new daemon.
        kill_daemon()
        daemonize(PID_PATH)
        run(options["dry_run"])
        print "Daemon started"
    else:
        # Start in the foreground.
        try:
            run(options["dry_run"])
        except KeyboardInterrupt:
            print
            print "Quitting"


if __name__ == "__main__":
    main()
