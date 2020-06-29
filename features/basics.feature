Feature: Basic stuff.

  Scenario: Add a target.

     when we add a target of "8.8.8.8" named "google.com"
     then there exists a target of "8.8.8.8" named "google.com"
