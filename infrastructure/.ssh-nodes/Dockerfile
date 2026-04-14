FROM docker:26-dind
RUN apk update && apk upgrade && apk add --no-cache openssh bash python3
RUN mkdir -p /root/.ssh && chmod 700 /root/.ssh
RUN sed -i s/#PermitRootLogin.*/PermitRootLogin\ yes/ /etc/ssh/sshd_config
RUN ssh-keygen -A
COPY id_rsa.pub /root/.ssh/authorized_keys
RUN chmod 600 /root/.ssh/authorized_keys
CMD ["sh", "-c", "dockerd-entrypoint.sh & /usr/sbin/sshd -D"]
