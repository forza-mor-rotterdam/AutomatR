# AutomatR

Applicatie voor geautomatiseerde taken in de MOR-keten

## Tech Stack

[Python](https://www.python.org/)

## Get Started 🚀

To get started, install [Docker](https://www.docker.com/)


### Start MOR core application

https://github.com/forza-mor-rotterdam/mor-core


### create docker network

```bash
    docker network create mor_bridge_network
```

### Build and run Docker container

```bash
    docker compose up
```

### Code style
Pre-commit is used for formatting and linting
Make sure pre-commit is installed on your system
```bash
    brew install pre-commit
```
and run
```bash
    pre-commit install
```

To manually run the pre-commit formatting run

```bash
    pre-commit run --all-files
```
Pre-commit currently runs black, flake8, autoflake, isort and some pre-commit hooks.


