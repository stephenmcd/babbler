"""
A Twitter bot that polls an RSS feed and posts the feed's titles at
random intervals as tweets, extracting words from the titles to use
as hashtags.
"""

from __future__ import with_statement
from cPickle import dump, load
from datetime import datetime
import logging
from optparse import OptionParser
from os import getcwd, remove
from os.path import join, dirname
from random import randint
from time import sleep

from feedparser import parse
from twitter import Api, TwitterError


__version__ = "0.1"


def wordfile(filename):
    """
    Returns a set word list from a file.
    Used for dictionary and stopwords.
    """
    with open(join(dirname(__file__), "wordfiles", filename)) as f:
        return set([s.strip() for s in f])

def main():
    """
    Get the entries from the feed and go through them, oldest first,
    adding them to the "todo" queue. Then take the first from the queue
    and post it to Twitter. Finally pause for a given time period between
    the min/max delay options.
    """

    DATA_PATH = join(getcwd(), "babbler.data")
    TWEET_MAX_LEN = 140
    dictionary = wordfile("dictionary.txt")
    stopwords = wordfile("stopwords.txt")

    parser = OptionParser(usage="usage: %prog [options]")

    parser.add_option("--hashtag-length-min", dest="hashtag_len_min",
                      default=3,
                      help="Minimum length of a hashtag")
    parser.add_option("--delay-min", dest="delay_min",
                      default=60*20,
                      help="Minimum number of seconds between posts")
    parser.add_option("--delay-max", dest="delay_max",
                      default=60*40,
                      help="Maximum number of seconds between posts")
    parser.add_option("--loglevel", dest="loglevel",
                      default="info", choices=("error", "info", "debug"),
                      help="Level of information printed")
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
        data = {"options": options, "todo": [], "done": set()}
    else:
        # Override any previously saved options with any values
        # provided via command line.
        for option in parser.option_list:
            if option.dest is not None:
                value = getattr(parsed_options, option.dest)
                if value is not None:
                    data["options"][option.dest] = value
        options = data["options"]

    # Set up logging.
    logging.basicConfig(format="%(asctime)s %(message)s")
    logging.getLogger().setLevel(getattr(logging, options["loglevel"].upper()))

    # Set up the Twitter API object.
    api = Api(**dict([(k, v) for k, v in options.items()
                      if k.split("_")[0] in ("consumer", "access")]))

    # Reset all data and delete tweets if specified.
    if parsed_options.destroy:
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
            exit()
        else:
            print "--DESTROY aborted"

    while True:

        # Go through the feed's entries, oldest first, and add new
        # entries to the "todo" list.
        todo = []
        feed = parse(options["feed_url"])
        try:
            logging.error("Feed error: %s" % feed["bozo_exception"])
        except KeyError:
            pass
        for entry in reversed(feed.entries):
            # Ignore entries that can't fit into a tweet, or are
            # already in "todo" or "done".
            if (len(entry["title"]) <= TWEET_MAX_LEN and
                entry["id"] not in [t["id"] for t in data["todo"]] and
                entry["id"] not in data["done"]):
                todo.append({"id": entry["id"], "title": entry["title"]})
        # Save the data file if new entries found.
        if todo:
            logging.debug("New entries in the queue: %s" % len(todo))
            data["todo"].extend(todo)
            with open(DATA_PATH, "wb") as f:
                dump(data, f)
        total = len(data["todo"])
        if total:
            logging.debug("Total entries in the queue: %s" % total)

        # Process the first entry in the "todo" list.
        if data["todo"]:

            tweet = data["todo"][0]["title"]

            # Add hashtags.
            #
            # 1) Get a list of non-dictionary words from the tweet
            #    with only alpha-numeric characters.
            # 2) Go through every word and if not a dictionary word,
            #    create up to 3 possible tags from it, the word
            #    combined with the previous word, the next word, and
            #    just the word itself. Only use previous/next words
            #    that aren't stopwords.
            # 3) Ignore all possible hashtags from the word if any of
            #    them have already been added as hashtags, eg via the
            #    previous or next word iteration, or a duplicate.
            # 4) Search for the possible hashtags via the API, giving
            #    each a score based on the sum of the seconds since
            #    epoch for each search result, and pick the highest
            #    scoring hashtag to use.
            # 5) Sort the hashtags found by score, and add as many as
            #    possible to the tweet within its length limit.

            # Initial word list.
            words = "".join([c for c in tweet.lower().replace("-", " ")
                             if c.isalnum() or c == " "]).split()
            hashtags = {}
            logging.debug("Getting hashtags for: %s" % tweet)
            for i, word in enumerate(words):
                if word not in dictionary:
                    possibles = [word]
                    if i > 0 and words[i-1] not in stopwords:
                        # Combined with previous word.
                        possibles.append(words[i-1] + word)
                    if i < len(words) - 1 and words[i+1] not in stopwords:
                        # Combined with next word.
                        possibles.append(word + words[i+1])
                    logging.debug("Possible hashtags from the word '%s': %s" %
                                  (word, ", ".join(possibles)))
                    # Check none of the possibilities have been used.
                    if [p for p in possibles if p in hashtags.keys()]:
                        logging.debug("Possible hashtags already used")
                    else:
                        highest = 0
                        hashtag = None
                        for possible in possibles:
                            if (len(possible) >= options["hashtag_len_min"] and
                                [c for c in possible if c.isalpha()]):
                                try:
                                    results = api.GetSearch("#" + possible)
                                except TwitterError, e:
                                    logging.error("Twitter error: %s" % e)
                                else:
                                    score = sum([t.created_at_in_seconds
                                                 for t in results])
                                    logging.debug("Score for '%s': %s" %
                                                  (possible, score))
                                    if score > highest:
                                        highest = score
                                        hashtag = possible
                        if hashtag:
                            hashtags[hashtag] = score

            # Sort hashtags by score and add to tweet.
            sort = lambda k: hashtags[k]
            hashtags = sorted(hashtags.keys(), key=sort, reverse=True)
            logging.debug("Hashtags found: %s" % (", ".join(hashtags)
                                                  if hashtags else "none"))
            for hashtag in hashtags:
                hashtag = " #" + hashtag
                if len(tweet + hashtag) <= TWEET_MAX_LEN:
                    tweet += hashtag

            # Post to Twitter.
            done = True
            try:
                api.PostUpdate(tweet)
            except TwitterError, e:
                logging.error("Twitter error: %s" % e)
                # Make the entry as done if it's a duplicate.
                done = str(e) == "Status is a duplicate."
            if done:
                logging.info("Tweeted: %s" % tweet)
                # Move the entry from "todo" to "done" and save the data file.
                data["done"].add(data["todo"].pop(0)["id"])
                with open(DATA_PATH, "wb") as f:
                    dump(data, f)

        # Pause between tweets - pause also occurs when no new entries
        # are found so that we don't hammer the feed URL.
        delay = randint(int(options["delay_min"]), int(options["delay_max"]))
        logging.debug("Pausing for %s seconds" % delay)
        sleep(delay)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print
        print "Quitting"
