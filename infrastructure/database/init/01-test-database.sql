-- Runs once, when the db volume is first created. Separate database for automated tests,
-- so tests never touch operational data.
CREATE DATABASE rei_test;
