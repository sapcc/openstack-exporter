FROM keppel.eu-de-1.cloud.sap/ccloud-dockerhub-mirror/library/alpine:3.12

LABEL source_repository="https://github.com/sapcc/openstack-exporter"
RUN apk --update add python3 openssl ca-certificates bash python3-dev  git py3-pip && \
    apk --update add --virtual build-dependencies libffi-dev openssl-dev libxml2 libxml2-dev libxslt libxslt-dev build-base
RUN git config --global http.sslVerify false
RUN git clone https://github.com/sapcc/openstack-exporter.git
RUN pip3 install --upgrade pip

ADD . openstack-exporter/
RUN cd openstack-exporter && pip3 install .

WORKDIR openstack-exporter
