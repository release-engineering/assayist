# Assayist

A system for discovering and tracing the composition of shipped products.

## Development

To setup a development environment:
* Create and activate a [Python virtual environment](https://virtualenv.pypa.io/en/stable/)
    (Python 3 is preferred)
* Install the API and its dependencies with:
  ```bash
  $ python setup.py develop
  ```

## Run the Unit Tests

Since the unit tests require a running Neo4j instance, the tests are run in Docker containers using
Docker Compose. The commands required to run the unit tests are abstracted in
`scripts/run-tests.sh`. This script will create the Docker image required to run the tests based
on `docker/Dockerfile-tests`, create a container with Neo4j, create another container to run
the tests based on the built Docker image, run the tests, and then delete the two created
containers.

To install Docker and Docker Compose on Fedora, run:

```bash
$ sudo dnf install docker docker-compose
```

To start Docker, run:

```bash
$ sudo systemctl start docker
```

To run the tests, run:

```bash
$ sudo scripts/run-tests.sh
```

To run just a single test, you can run:

```bash
$ sudo scripts/run-tests.sh pytest3 -vvv tests/test_file::test_name
```

## Code Styling

The codebase conforms to the style enforced by `flake8` with the following exceptions:
* The maximum line length allowed is 100 characters instead of 80 characters

In addition to `flake8`, docstrings are also enforced by the plugin `flake8-docstrings` with
the following exemptions:
* D100: Missing docstring in public module
* D104: Missing docstring in public package

The format of the docstrings should be in the Sphynx style such as:

```
Get a resource from Neo4j.

:param str resource: a resource name that maps to a neomodel class
:param str uid: the value of the UniqueIdProperty to query with
:return: a Flask JSON response
:rtype: flask.Response
:raises NotFound: if the item is not found
:raises ValidationError: if an invalid resource was requested
```
