# Sandbox image: language toolchains, the trusted runner and its launcher.
# No application code and no credentials. The full python:3.12 image (Debian,
# buildpack-deps based) already ships GCC/G++ 14, so no package manager runs
# at build time. Future improvement: per-language slim images (docs/SECURITY.md).
FROM python:3.12

COPY launcher.c /opt/runner/launcher.c
RUN gcc -O2 -static -Wall -Wextra -o /opt/runner/cf-launch /opt/runner/launcher.c \
 && rm /opt/runner/launcher.c \
 && chmod 0555 /opt/runner/cf-launch

COPY runner.py /opt/runner/runner.py
RUN chmod 0555 /opt/runner/runner.py \
 && mkdir -p /sandbox && chmod 1777 /sandbox

WORKDIR /sandbox
CMD ["/usr/local/bin/python3", "-I", "-B", "/opt/runner/runner.py"]
