ARG BUILD_FROM
FROM $BUILD_FROM

# Install bash and curl for run.sh
RUN apk add --no-cache bash curl

# Copy add-on files
COPY run.sh /
COPY payload /payload

RUN chmod a+x /run.sh

CMD ["/run.sh"]
