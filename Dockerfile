FROM keppel.eu-de-1.cloud.sap/ccloud-dockerhub-mirror/library/alpine:3.20

LABEL source_repository="https://github.com/sapcc/openstack-exporter"
RUN apk --update add python3 openssl ca-certificates bash python3-dev git py3-pip && \
    apk --update add --virtual build-dependencies libffi-dev openssl-dev libxml2 \
    libxml2-dev libxslt libxslt-dev build-base rust cargo
RUN git config --global http.sslVerify false

ADD . /app/openstack-exporter/
WORKDIR /app/openstack-exporter

RUN python3 -m venv /app/venv
RUN /app/venv/bin/pip install --upgrade pip setuptools_rust
RUN /app/venv/bin/pip install .

COPY run.sh /app/run.sh
RUN chmod +x /app/run.sh

# Create symlink for backwards compatibility with helm chart
RUN ln -s /app/run.sh /usr/bin/openstack_exporter

ENTRYPOINT ["/app/run.sh"]
