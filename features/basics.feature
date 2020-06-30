Feature: Basic stuff.

  Scenario: Add a target through the UI endpoints.

     when we request a histogram for target "8.8.8.8"
     then we get a response with status code 404
     when we add a target of "8.8.8.8" named "google.com"
     then there exists a target of "8.8.8.8" named "google.com"
     when we wait 2 seconds
     when we request a histogram for target "8.8.8.8"
     then we get a response with status code 200
     when we delete a target of "8.8.8.8"
     then there exists no target of "8.8.8.8"

  Scenario: Same thing through the peering endpoints.

  Scenario: Add a target through the UI endpoints and see that it gets dist'ed to peers.

    These targets are NOT foreign, thus shall be distributed.

  Scenario: Add a target through the peering endpoints and see that it does NOT get dist'ed to peers.

    These targets are foreign, thus shall NOT be distributed.
