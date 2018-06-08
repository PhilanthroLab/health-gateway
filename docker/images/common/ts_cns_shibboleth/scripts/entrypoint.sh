#!/bin/bash
if [[ -z ${SERVER_NAME} ]]; then
    echo "Server name not found. Set SERVER_NAME env variable."
    exit 1
fi

SHIBBOLETH_BASE_DIR=/opt/shibboleth-idp
SHIBBOLETH_CREDENTIALS_DIR=${SHIBBOLETH_BASE_DIR}/credentials
SHIBBOLETH_METADATA=${SHIBBOLETH_BASE_DIR}/metadata/idp-metadata.xml

for f in idp-backchannel idp-signing idp-encryption; do
    if [[ ! -f ${SHIBBOLETH_CREDENTIALS_DIR}/${f}.crt ]]; then
        echo "$f.crt not found. You should mount it in $SHIBBOLETH_CREDENTIALS_DIR/$f.crt"
        exit 1
    fi

    if [[ "$f" != "idp-backchannel" ]]; then
        if [[ ! -f ${SHIBBOLETH_CREDENTIALS_DIR}/${f}.key ]]; then
            echo "$f.key not found. You should mount it in $SHIBBOLETH_CREDENTIALS_DIR/$f.key"
            exit 1
        fi
    else
        if [[ ! -f ${SHIBBOLETH_CREDENTIALS_DIR}/${f}.p12 ]]; then
            echo "$f.p12 not found. You should mount it in $SHIBBOLETH_CREDENTIALS_DIR/$f.p12"
            exit 1
        fi
    fi
done

/container/replace_certs.sh
/opt/shibboleth-idp/bin/build.sh

if [[ -z "${DEVELOPMENT}" ]]; then
    envsubst '${SERVER_NAME}' < /etc/apache2/sites-available/shibboleth-virtual-host.prod.conf.template > /etc/apache2/sites-available/shibboleth-virtual-host.prod.conf
    a2ensite shibboleth-virtual-host.prod.conf
else
    envsubst '${SERVER_NAME}' < /etc/apache2/sites-available/shibboleth-virtual-host.dev.conf.template > /etc/apache2/sites-available/shibboleth-virtual-host.dev.conf
    a2ensite shibboleth-virtual-host.dev.conf
fi
apache2ctl start

envsubst '${SERVER_NAME}' < /opt/shibboleth-idp/conf/idp.properties.template > /opt/shibboleth-idp/conf/idp.properties

#JAVA_OPTS="-Djava.awt.headless=true -XX:+UseConcMarkSweepGC -Djava.util.logging.config.file=/var/lib/tomcat8/conf/logging.properties" 
CATALINA_TMPDIR=/tmp/ \
CATALINA_PID="/var/run/tomcat8.pid" \
CATALINA_HOME=/usr/share/tomcat8 \
CATALINA_BASE=/var/lib/tomcat8 \
JSSE_HOME=/usr/lib/jvm/java-8-oracle/jre/ \
/usr/share/tomcat8/bin/catalina.sh run