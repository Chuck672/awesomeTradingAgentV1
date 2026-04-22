import datetime
import sys

print(f"Earliest: {datetime.datetime.fromtimestamp(1765148400, tz=datetime.timezone.utc)}")
print(f"Latest:   {datetime.datetime.fromtimestamp(1775221200, tz=datetime.timezone.utc)}")
