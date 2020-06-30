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

     when we request a histogram for target "1.1.1.1"
     then we get a response with status code 404
     when a peer sends us a target of "1.1.1.1" named "cloudflare.com"
     then there exists a target of "1.1.1.1" named "cloudflare.com"
     when we wait 2 seconds
     when we request a histogram for target "1.1.1.1"
     then we get a response with status code 200

  Scenario: Add a target through the UI endpoints and see that it gets dist'ed to peers.

    These targets are NOT foreign, thus shall be distributed.

     when we request a histogram for target "1.2.3.4"
     then we get a response with status code 404
     when we add a target of "1.2.3.4" named "dummycorp.com"
     then there exists a target of "1.2.3.4" named "dummycorp.com"
      and we send a target of "1.2.3.4" named "dummycorp.com" to our peers

  Scenario: Add a target through the peering endpoints and see that it does NOT get dist'ed to peers.

    These targets are foreign, thus shall NOT be distributed.

     when we request a histogram for target "4.3.2.1"
     then we get a response with status code 404
     when a peer sends us a target of "4.3.2.1" named "othercorp.com"
     then there exists a target of "4.3.2.1" named "othercorp.com"
      and we do not send a target of "4.3.2.1" to our peers
