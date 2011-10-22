"""
A Twitter bot that polls an RSS feed and posts the feed's titles
at random intervals as tweets, extracting non-dictionary words
from the titles to use as hashtags.
"""

from cPickle import dump, load
from datetime import datetime
from optparse import OptionParser
from os import getcwd
from os.path import join
from random import randint
from time import sleep

from feedparser import parse
from twitter import Api


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
        data = {"options": options, "entries": {}}
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

    while True:
        for entry in reversed(parse(options["feed_url"]).entries):
            # Ignore saved entries or those that can't fit into a tweet.
            saved = entry["id"] in data["entries"]
            if saved or len(entry["title"]) > TWEET_MAX_LEN:
                continue
            # Save the entry to the data file.
            data["entries"][entry["id"]] = entry["title"]
            with open(DATA_PATH, "wb") as f:
                dump(data, f)
            # Add hashtags - get a list of non-dictionary words
            # from the title with only alpha characters that are
            # longer than 3 characters, and add them to the tweet,
            # longest hashtags first, if they don't make the tweet
            # too long and have been used as hashtags by others.
            chars = "".join([c for c in entry["title"].lower()
                             if c.isalnum() or c == " "])
            tags = [w for w in chars.split() if w not in words and
                    len(w) >= options["hashtag_len_min"]]
            for tag in sorted(tags, key=len, reverse=True):
                tag = " #" + tag
                if (len(entry["title"] + tag) <= TWEET_MAX_LEN and
                    api.GetSearch(tag.strip())):
                    entry["title"] += tag
            # Post to Twitter and cancel checking the remaining
            # entries so that we can pause between tweets.
            print entry["title"]
            api.PostUpdate(entry["title"])
            break

        # Pause between tweets - pause also occurs when no new entries
        # are found so that we don't hammer the feed URL.
        sleep(randint(int(options["delay_min"]), int(options["delay_max"])))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print
        print "Quitting"
