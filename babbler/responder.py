
import logging
from random import choice
import re
from string import punctuation

from yaml import load

from babbler.feed import Feed


class RespondingFeed(Feed):
    """
    Extends Feed to also check for replies on Twitter, adding
    replies generated from Eliza responses as entries to tweet.
    """

    def setup(self, options):
        """
        Store the Twitter API reference, load the Eliza grammar and
        set up the feed's options.
        """
        self.twitter = options.pop("twitter")
        with open(options.pop("eliza_path")) as f:
            grammar = load(f)
            self.reflections = grammar["reflections"]
            self.patterns = [(re.compile(item.keys()[0], re.IGNORECASE),
                             item.values()[0]) for item in grammar["patterns"]]
        super(RespondingFeed, self).setup(options)

    def __getstate__(self):
        """
        Twitter object can't be pickled, so remove it.
        """
        state = dict(self.__dict__)
        try:
            del state["twitter"]
        except KeyError:
            pass
        return state

    def entries(self):
        """
        Go through each of the mentions and if they're direct replies,
        create an Eliza response and return it as a feed entry with
        the mention's ID.
        """
        entries = []
        saved = self.saved()
        for mention in self.twitter.GetMentions():
            if mention.in_reply_to_screen_name and mention.id not in saved:
                to_name = "@" + mention.in_reply_to_screen_name
                from_name = "@" + mention.user.screen_name
                # The mention is a reply if it starts with the same
                # username as the "in_reply_to_screen_name" attribute.
                reply = (to_name.lstrip("@") and
                         mention.text.lower().startswith(to_name.lower()))
                # Remove our own username from the text.
                text = mention.text[len(to_name) + 1:]
                # Ignore links as they're probably spam.
                if not reply or "http" in text.lower():
                    self.done.add(mention.id)
                else:
                    logging.debug("Reply found %s: %s" % (from_name, text))
                    # Since the responses are partially random, try
                    # up to 3 times if the response is too long.
                    tries = 3
                    while True:
                        response = self.response(text)
                        response_with_from = "%s %s" % (from_name, response)
                        if len(response_with_from) > self.max_len:
                            logging.debug("Response too long: %s" %
                                          response_with_from)
                            response = None
                            tries -= 1
                            if tries > 0:
                                logging.debug("Retrying")
                                continue
                        break
                    if response is not None:
                        entries.append({
                            "id": mention.id,
                            "title": response,
                            "to": from_name
                        })
        # Combine responses with feed entries, prioritizing responses
        # over feed entries.
        return entries + super(RespondingFeed, self).entries()

    """
    The response and translate methods adopted from:
    http://www.jezuk.co.uk/cgi-bin/view/software/eliza
    """

    def response(self, text):
        """
        Matches the given text to one of the response patterns.
        """
        for pattern, responses in self.patterns:
            match = pattern.match(text)
            if match:
                response = choice(responses)
                # Switch reflections.
                while True:
                    pos = response.find("%")
                    if pos == -1:
                        break
                    switch = self.translate(match.group(int(response[pos + 1])))
                    response = response[:pos] + switch + response[pos + 2:]
                # Remove extraneous punctuation.
                while len(response.rstrip(punctuation)) + 1 < len(response):
                    response = response[:-2] + response[-1]
                return response

    def translate(self, match):
        """
        Translates reflections.
        """
        words = match.lower().split()
        for i, word in enumerate(words):
            try:
                words[i] = self.reflections[word]
            except KeyError:
                pass
        return " ".join(words)
