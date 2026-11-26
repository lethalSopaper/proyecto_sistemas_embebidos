FROM nodered/node-red:5.0.10-debian

USER root
COPY --chown=node-red:node-red package.json package-lock.json /opt/gps/
RUN cd /opt/gps && npm ci --omit=dev

COPY --chown=node-red:node-red entrypoint.sh /opt/gps/entrypoint.sh
COPY --chown=node-red:node-red install-flows.js settings.js gps-repository.js routes.html flows.json /opt/gps/
RUN chmod 0755 /opt/gps/entrypoint.sh

USER node-red
ENTRYPOINT ["/opt/gps/entrypoint.sh"]
