"""Domain limits shared by the ORM models (column sizes) and the API schemas (validation).

Keeping them in one place guarantees that a value accepted by the API always fits the database.
"""

from typing import Final

# Upper bound of PostgreSQL INTEGER: larger ids/quantities would fail in the database with a 500.
PG_INT_MAX: Final = 2_147_483_647

NAME_MAX_LENGTH: Final = 255
DESCRIPTION_MAX_LENGTH: Final = 5_000

# Prices are NUMERIC(10, 2): up to 99 999 999.99.
MONEY_PRECISION: Final = 10
MONEY_SCALE: Final = 2
# Order totals are NUMERIC(16, 2): up to 99 999 999 999 999.99.
ORDER_TOTAL_PRECISION: Final = 16
