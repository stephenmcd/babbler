"""
A Twitter bot that polls an RSS feed and posts the feed's titles
at random intervals as tweets, extracting non-dictionary words
from the titles to use as hashtags.
"""

from cPickle import dump, load
from datetime import datetime
from os import getcwd
from os.path import join
from random import randint
from string import letters
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
    the min/max delay settings.
    """

    # Initial settings.
    settings = {
        "data_path": join(getcwd(), "babbler.data"),
        "words_path": "/usr/share/dict/words",
        "tweet_max_len": 140,
    }

    # Settings entered by user.
    user_entered = (
        ("feed_url", "RSS Feed URL"),
        ("delay_min", "Minimum number of seconds between posts"),
        ("delay_max", "Maximum number of seconds between posts"),
        ("consumer_key", "Twitter Application Consumer Key"),
        ("consumer_secret", "Twitter Application Consumer Secret"),
        ("access_token_key", "Twitter Account Access Key"),
        ("access_token_secret", "Twitter Account Access Secret"),
    )

    try:
        # Try and load a previously saved data file.
        with open(settings["data_path"], "rb") as f:
            data = load(f)
        settings = data["settings"]
    except IOError:
        # If no data file exists, prompt the user for the required settings
        # and create the data file, persisting the entered settings.
        print
        print "Initial setup."
        print "All data will be saved to '%s'" % settings["data_path"]
        print "Press CTRL C to abort."
        print
        for k, v in user_entered:
            settings[k] = raw_input("Please enter '%s': " % v)
        data = {"settings": settings, "entries": {}}

    # Load the dictionary words file. Given the typical UNIX dictionary,
    # we're not interested in names of things (uppercase words) or
    # duplicate possesive apostophes as we'll strip apostrophes when
    # determining hashtags.
    with open(settings["words_path"], "r") as f:
        words = set([s.strip().replace("'", "") for s in f if s[0].islower()])

    # Set up the Twitter API object.
    api = Api(**dict([(k, v) for k, v in settings.items()
                      if k.split("_")[0] in ("consumer", "access")]))

    while True:
        for entry in reversed(parse(settings["feed_url"]).entries):
            # Ignore saved entries or those that can't fit into a tweet.
            saved = entry["id"] in data["entries"]
            if saved or len(entry["title"]) > settings["tweet_max_len"]:
                continue
            # Save the entry to the data file.
            data["entries"][entry["id"]] = entry["title"]
            with open(settings["data_path"], "wb") as f:
                dump(data, f)
            # Add hashtags - get a list of non-dictionary words
            # from the title with only alpha characters that are
            # longer than 3 characters, and add them to the tweet,
            # longest hashtags first, if they don't make the tweet
            # too long.
            alpha = letters + " "
            chars = "".join([c for c in entry["title"].lower() if c in alpha])
            tags = [w for w in chars.split() if w not in words and len(w) > 3]
            for tag in sorted(tags, key=len, reverse=True):
                tag = " #" + tag
                if len(entry["title"] + tag) <= settings["tweet_max_len"]:
                    entry["title"] += tag
            # Post to Twitter and cancel checking the remaining
            # entries so that we can pause between tweets.
            print entry["title"]
            api.PostUpdate(entry["title"])
            break

        # Pause between tweets - pause also occurs when no new entries
        # are found so that we don't hammer the feed URL.
        sleep(randint(int(settings["delay_min"]), int(settings["delay_max"])))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print
        print "Quitting"
