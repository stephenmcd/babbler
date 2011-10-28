
Babbler
=======

A Twitter bot that polls an RSS feed and posts the feed's titles as
tweets, extracting words from the titles to use as hashtags.

After installing the 'babbler' command will be available which you
can use to run the bot. Data will be stored in the current directory.

Options
-------

  --version             show program's version number and exit
  -h, --help            show this help message and exit

  Required:
    -u url, --feed-url=url
                        RSS Feed URL

  Optional:
    -i strings, --ignore=strings
                        Comma separated strings for ignoring feed entries if
                        they contain any of the strings
    -p seconds, --pause=seconds
                        Seconds between RSS feed requests (default:600)
    -q decimal, --queue-slice=decimal
                        Decimal fraction of unposted tweets to send during
                        each iteration between feed requests (default:0.3)
    -l level, --log-level=level
                        Level of information printed (ERROR|INFO|DEBUG)
                        (default:INFO)
    -m len, --hashtag-min-length=len
                        Minimum length of a hashtag (default:3)

  Switches:
    -a, --append        Switch certain options into append mode where their
                        values provided are appended to their persisted
                        values, namely --ignore, --hashtag-min-length,
                        --pause, --queue-slice
    -s, --subtract      Opposite of --append
    -e, --edit-data     Load a Python shell for editing the data file
    -f, --dry-run       Fake run that doesn't save data or post tweets
    -d, --daemonize     Run as a daemon
    -k, --kill          Kill a previously started daemon
    -D, --DESTROY       Deletes all saved data and tweets from Twitter

  Twitter authentication (all required):
    -w key, --consumer-key=key
                        Twitter Consumer Key
    -x secret, --consumer-secret=secret
                        Twitter Consumer Secret
    -y key, --access-token-key=key
                        Twitter Access Token Key
    -z secret, --access-token-secret=secret
                        Twitter Access Token Secret

Options need only be provided once via command line as options specified are
then persisted in the data file, and reused on subsequent runs. Required
options can also be omitted as they will each then be prompted for
individually.
