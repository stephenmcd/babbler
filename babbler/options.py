
from optparse import OptionGroup, OptionParser

from yaml import load


class Options(dict):
    """
    Wrapper for OptionParser - handles loading options from YAML,
    prompting for missing required options, and handling switches
    for appending or subtracting to default option values.
    """

    def __init__(self, yaml_path, **kwargs):
        """
        Set up args and OptionParser.
        """
        # Load YAML file and create OptionParser.
        with open(yaml_path) as f:
            data = load(f)
        kwargs["usage"] = "usage: %prog [options]"
        kwargs["epilog"] = data["epilog"]
        existing = kwargs.pop("existing")
        self.parser = OptionParser(**kwargs)

        # Set Options specific attributes.
        self.appendable = data["appendable"]
        self.append_option = data["append option"]
        self.subtract_option = data["subtract option"]
        self.defaults = data["defaults"]

        # Add each OptionGroup.
        formatting = {"appendable": ", ".join(data["appendable"])}
        for option_group in data["options"]:
            for name, options in option_group.items():
                group = OptionGroup(self.parser, name)
                for option in options:
                    formatting["default"] = self.defaults.get(option["dest"])
                    formatting["choices"] = "|".join(option.get("choices", []))
                    if option.get("action") == "store_true":
                        option["default"] = False
                    elif option.get("action") == "store_false":
                        option["default"] = True
                    option["help"] %= formatting
                    group.add_option(*option.pop("args"), **option)
                self.parser.add_option_group(group)
        self.defaults.update(existing)

    def append(self, option, value):
        """
        Append the value to the default in append mode.
        """
        default = self.defaults.get(option.dest)
        if value is None or default is None:
            return value
        if option.type == "string" and not value.startswith(","):
            value = "," + value
        return default + value

    def subtract(self, option, value):
        """
        Subtract the value from the default in subtract mode.
        """
        default = self.defaults.get(option.dest)
        if value is None or default is None:
            return value
        if option.type == "string" and not value.startswith(","):
            default = set(default.split(","))
            value = set(value.split(","))
            return ",".join(default - value)
        else:
            return default - value

    def all_options(self):
        """
        Flatten all options for all groups.
        """
        return [o for g in self.parser.option_groups for o in g.option_list]

    def parse_args(self):
        """
        Call OptionParser's parse_args() and handle defaults, append,
        subtract and prompting for missing options.
        """
        parsed, _ = self.parser.parse_args()
        final = {}
        append = getattr(parsed, self.append_option)
        subtract = getattr(parsed, self.subtract_option)
        for option in self.all_options():
            name = option.dest
            if name is not None:
                value = getattr(parsed, name)
                default = self.defaults.get(name)
                if append and option.get_opt_string() in self.appendable:
                    value = self.append(option, value)
                elif subtract and option.get_opt_string() in self.appendable:
                    value = self.subtract(option, value)
                if value is None:
                    value = default
                if value is None:
                    value = raw_input("Please enter '%s': " % option.help)
                self[name] = value
        return self

    def __str__(self):
        """
        Format the options.
        """
        formatted = []
        padding = len(max(self.keys(), key=len)) + 5
        for option in self.all_options():
            name = (option.dest + ": ").ljust(padding, ".")
            value = self[option.dest]
            formatted.append("%s %s" % (name, value))
        return "\n".join(formatted)
