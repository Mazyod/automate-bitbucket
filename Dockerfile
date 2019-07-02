FROM python:3-alpine

VOLUME /app
WORKDIR /app
EXPOSE 8448

CMD ["./run.sh"]
