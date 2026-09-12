FROM golang:1.22-bookworm AS builder

WORKDIR /src
COPY go.mod ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /out/girly-server .

FROM python:3.12-slim

WORKDIR /app
COPY --from=builder /out/girly-server /app/girly-server
COPY web /app/web
COPY assistant /app/assistant
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh && mkdir -p /app/data

ENV GIRLY_WEB=/app/web
ENV GIRLY_DATA=/app/data/girly.json
ENV GIRLY_ASSISTANT=http://127.0.0.1:3000

EXPOSE 8080
CMD ["/app/start.sh"]
