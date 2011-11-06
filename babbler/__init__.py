#!/usr/bin/env python

"""
A Twitter bot that polls an RSS feed and posts its entries as tweets,
with auto-generated hashtags. For extra mischief, replies to the bot
are responded to using a basic Eliza implementation.

After installing, the 'babbler' command will be available which you
can use to run the bot. Data will be stored in the current directory.
"""


__version__ = "0.3"


def main():
    """
    Main entry point for the program.
    """
    from babbler.bot import Bot
    bot = Bot(description=__doc__.strip(), version=__version__)

    if bot.data["options"]["destroy"]:
        # Reset all data and delete tweets if specified.
        bot.destroy()
    elif bot.data["options"]["kill"]:
        # Kill a previously started daemon.
        if bot.kill():
            print "Daemon killed"
        else:
            print "Couldn't kill daemon"
    elif bot.data["options"]["edit_data"]:
        # Run a Python shell for editing data.
        bot.edit()
    elif bot.data["options"]["daemonize"]:
        # Start a new daemon.
        bot.run(as_daemon=True)
        print "Daemon started"
    else:
        # Start in the foreground.
        try:
            bot.run()
        except KeyboardInterrupt:
            print
            print "Quitting"


if __name__ == "__main__":
    import os, sys; sys.path.insert(0, os.getcwd())
    main()
