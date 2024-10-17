pulsar offers the standard OpenaAI compatible endpoints, compatible with the OAIServer API standard.
by deafult the server generate a new token for the sesison and byu choice it accets only requests from the same network. 
to make thing the right way you should send a request to your localserverby going first inisde the config folder( so you have access to the .env file) nad make a bearer auth reuqest to  /users/list , get the token and include it inth eheader (or in the clinet if you are using the OAI sdk) 
you can also disable auth by setting allow_unsafe_local_requests to true in the config file found Edit the `last.yaml` configuration file, typically located at:

- 🐧 Linux/Mac: `~/pulsar/configs`
- 🪟 Windows: `%userprofile%\pulsar\configs`
