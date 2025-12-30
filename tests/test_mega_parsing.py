import logging

from megatui.mega.data import (
    MegaSizeUnits,
)
from megatui.mega.megacmd import (
    _speedlimit_parsed,  # pyright: ignore[reportPrivateUsage]
)

logger = logging.getLogger(__name__)


class TestSpeedLimitParsing:
    def test_parsing_single_lines(self):
        """Test the logic of converting a single text line into a SpeedLimit object.
        Target function: _speedlimit_parsed.
        """
        # Case 1: Parsing Megabytes
        # Input: String from MEGAcmd
        line_mb = "Upload speed limit = 52428800 B/s"
        # Action: Parse it
        logger.debug("Parsing: '%s'", line_mb)
        result_mb = _speedlimit_parsed(line_mb)
        # Check Logic:
        assert result_mb
        assert result_mb.transfer_limit == 50.0
        assert result_mb.units.value == MegaSizeUnits.MB.value
        logger.debug("RESULT: '%s %s'", result_mb.transfer_limit, result_mb.units.name)

        # Case 2: Parsing Bytes
        line_b = "Download speed limit = 100 B/s"
        logger.debug("Parsing: '%s'", line_b)
        result_b = _speedlimit_parsed(line_b)
        assert result_b
        assert result_b.transfer_limit == 100.0
        assert result_b.units.value == MegaSizeUnits.B.value

        logger.debug("RESULT: '%s %s'", result_b.transfer_limit, result_b.units.name)

        # Case 3: Parsing Unlimited

        line_unlimited = "Upload speed limit = unlimited"
        logger.debug("Parsing: '%s'", line_unlimited)
        result_unlimited = _speedlimit_parsed(line_unlimited)

        assert result_unlimited is None
        logger.debug("RESULT: '%s'", result_unlimited)
