"""
A Twitter bot that polls an RSS feed and posts the feed's titles
at random intervals as tweets, extracting non-dictionary words
from the titles to use as hashtags.
"""

from cPickle import dump, load
from datetime import datetime
from optparse import OptionParser
from os import getcwd, remove
from os.path import join
from random import randint
from time import sleep

from feedparser import parse
from twitter import Api, TwitterError


__version__ = "0.1"


def main():
    """
    Get the entries from the feed and go through them, oldest first.
    If the entry hasn't been saved to the data file, extract hashtags
    from it and post it to Twitter, and then abort entries for the
    rest of the feed. Finally pause for a given time period between
    the min/max delay options.
    """

    DATA_PATH = join(getcwd(), "babbler.data")
    TWEET_MAX_LEN = 140

    parser = OptionParser(usage="usage: %prog [options]")

    parser.add_option("--words-path", dest="words_path",
                      default="/usr/share/dict/words",
                      help="Path to dictionary file.")
    parser.add_option("--hashtag-length-min", dest="hashtag_len_min",
                      default=3,
                      help="Minimum length of a hashtag")
    parser.add_option("--delay-min", dest="delay_min",
                      default=60*20,
                      help="Minimum number of seconds between posts")
    parser.add_option("--delay-max", dest="delay_max",
                      default=60*40,
                      help="Maximum number of seconds between posts")
    parser.add_option("--DESTROY", dest="destroy",
                      default=False, action="store_true",
                      help="Deletes all saved data and tweets from Twitter")

    parser.add_option("--feed-url", dest="feed_url",
                      help="RSS Feed URL")
    parser.add_option("--consumer-key", dest="consumer_key",
                      help="Twitter Application Consumer Key")
    parser.add_option("--consumer-secret", dest="consumer_secret",
                      help="Twitter Application Consumer Secret")
    parser.add_option("--access-token-key", dest="access_token_key",
                      help="Twitter Access Token Key")
    parser.add_option("--access-token-secret", dest="access_token_secret",
                      help="Twitter Access Token Secret")

    (parsed_options, args) = parser.parse_args()

    try:
        # Try and load a previously saved data file.
        with open(DATA_PATH, "rb") as f:
            data = load(f)
    except IOError:
        # If no data file exists, prompt the user for the required options
        # and create the data file, persisting the entered options.
        print
        print "Initial setup."
        print "All data will be saved to '%s'" % DATA_PATH
        print "Press CTRL C to abort."
        print
        options = {}
        for option in parser.option_list:
            if option.dest is not None:
                value = getattr(parsed_options, option.dest)
                if value is None:
                    value = raw_input("Please enter '%s': " % option.help)
                options[option.dest] = value
        data = {"options": options, "todo": [], "done": {}}
    else:
        # Override any previously saved options with any values
        # provided via command line.
        for option in parser.option_list:
            if option.dest is not None:
                value = getattr(parsed_options, option.dest)
                if value is not None:
                    data["options"][option.dest] = value
        options = data["options"]

    # Load the dictionary words file. Given the typical UNIX dictionary,
    # we're not interested in names of things (uppercase words) or
    # duplicate possesive apostophes as we'll strip apostrophes when
    # determining hashtags.
    with open(options["words_path"], "r") as f:
        words = set([s.strip().replace("'", "") for s in f if s[0].islower()])

    # Set up the Twitter API object.
    api = Api(**dict([(k, v) for k, v in options.items()
                      if k.split("_")[0] in ("consumer", "access")]))

    # Reset all data and delete tweets if specified.
    if parsed_options.destroy:
        print
        print "WARNING: You have specified the --DESTROY option"
        print "All tweets will be deleted from your account."
        if raw_input("Enter 'y' to continue. ").strip().lower() == "y":
            print "Deleting all data and tweets."
            remove(DATA_PATH)
            while True:
                tweets = api.GetUserTimeline()
                if not tweets:
                    break
                for tweet in tweets:
                    try:
                       api.DestroyStatus(tweet.id)
                    except TwitterError:
                        pass
            exit()
        else:
            print "--DESTROY aborted"

    while True:

        # Go through the feed's entries, oldest first, and add new
        # entries to the "todo" list.
        todo = []
        feed = parse(options["feed_url"])
        try:
            print "Feed error: %s" % feed["bozo_exception"]
        except KeyError:
            pass
        for entry in reversed(feed.entries):
            # Ignore entries that can't fit into a tweet, or are
            # already in "todo" or "done".
            if (len(entry["title"]) <= TWEET_MAX_LEN and
                entry["id"] not in [t["id"] for t in data["todo"]] and
                entry["id"] not in data["done"]):
                new_entries = True
                todo.append({"id": entry["id"], "title": entry["title"]})
        # Save the data file if new entries found.
        if todo:
            print "%s new entries added to the queue." % len(todo)
            data["todo"].extend(todo)
            with open(DATA_PATH, "wb") as f:
                dump(data, f)
        print "%s entries are in the queue." % len(data["todo"])

        # Process the first entry in the "todo" list.
        if data["todo"]:
            entry = data["todo"][0]
            # Add hashtags - get a list of non-dictionary words
            # from the title with only alpha characters that meet
            # the minimum hashtag length, and add them to the tweet,
            # longest hashtags first, if they don't make the tweet
            # too long and have been used as hashtags by other people.
            chars = "".join([c for c in entry["title"].lower()
                             if c.isalnum() or c == " "])
            tags = set([w for w in chars.split() if w not in words and
                        len(w) >= options["hashtag_len_min"]])
            for tag in sorted(tags, key=len, reverse=True):
                tag = " #" + tag
                if (len(entry["title"] + tag) <= TWEET_MAX_LEN and
                    api.GetSearch(tag.strip())):
                    entry["title"] += tag
            # Post to Twitter.
            done = True
            try:
                api.PostUpdate(entry["title"])
            except TwitterError, e:
                print "Twitter error: %s" % e
                # Make the entry as done if it's a duplicate.
                done = str(e) == "Status is a duplicate."
            if done:
                print "Tweeted: %s" % entry["title"]
                # Move the entry from "todo" to "done" and save the data file.
                data["done"][entry["id"]] = entry["title"]
                del data["todo"][0]
                with open(DATA_PATH, "wb") as f:
                    dump(data, f)

        # Pause between tweets - pause also occurs when no new entries
        # are found so that we don't hammer the feed URL.
        sleep(randint(int(options["delay_min"]), int(options["delay_max"])))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print
        print "Quitting"
