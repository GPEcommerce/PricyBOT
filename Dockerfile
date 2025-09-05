# Use a full Debian base image
FROM debian:bookworm

# Set non-interactive mode for installations
ENV DEBIAN_FRONTEND=noninteractive

# Combine all installation steps into a single RUN command for efficiency
RUN apt-get update && \
    apt-get install -y \
        wget \
        gnupg \
        xvfb \
        python3 \
        python3-pip \
        dos2unix \
        fonts-noto-color-emoji \
        fonts-liberation \
        fonts-indic \
        fonts-thai-tlwg && \
    wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome-keyring.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    apt-get install -y google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# Create the user and work directory first (still as root)
RUN useradd --create-home appuser
WORKDIR /home/appuser/app

# Copy application files and set ownership of the files
COPY --chown=appuser:appuser . .

# *** NEW STEP: Grant ownership of the work directory to the user ***
RUN chown -R appuser:appuser /home/appuser/app

# Run file modifications and permission changes (still as root)
RUN dos2unix /home/appuser/app/entrypoint.sh && \
    chmod +x /home/appuser/app/entrypoint.sh

# Install Python dependencies
RUN pip install --no-cache-dir --break-system-packages --upgrade pip && \
    pip install --no-cache-dir --break-system-packages -r requirements.txt

# --- NOW, SWITCH TO THE NON-ROOT USER ---
USER appuser

# Expose the application port
EXPOSE 8000

# Set the command to run on container start
CMD ["/home/appuser/app/entrypoint.sh"]