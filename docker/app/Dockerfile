FROM python:3.9-slim-buster as builder

WORKDIR /app

# copy poetry files to workdir
COPY pyproject.toml poetry.lock ./

# install poetry
RUN pip install --no-cache-dir -U pip setuptools wheel poetry &&\
    # set poetry configuration settings
    poetry config virtualenvs.in-project true &&\
    # install all project dependencies with poetry (incl. dev)
    poetry install --no-root --no-interaction --no-ansi

FROM python:3.9-slim-buster

ARG user
ARG password
ARG virtual_env=/usr/src/.venv
# override DEBIAN_FRONTEND during the installation process
ARG DEBIAN_FRONTEND=noninteractive

WORKDIR /usr/src/app

# install system packages
RUN apt-get update &&\
    apt-get upgrade -y &&\
    apt-get install --no-install-recommends -y -q \
            sudo \
            netcat &&\
    # cleanup
    apt-get autoremove -y &&\
    apt-get clean &&\
    rm -rf /var/lib/apt/lists &&\
    # add new user with sudo privileges
    useradd --no-create-home --user-group --groups sudo -s /bin/bash $user &&\
    # set user password
    echo "$user:$password" | chpasswd

# copy venv from builder
COPY --chown=$user:$user --from=builder /app/.venv $virtual_env

# update the "PATH" variable
ENV PATH="$virtual_env/bin:$PATH"

USER $user

CMD ["/bin/bash"]
