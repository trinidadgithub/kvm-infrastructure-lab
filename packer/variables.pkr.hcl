variable "ssh_private_key" {
  description = "Absolute path to an unencrypted build SSH private key; set PKR_VAR_ssh_private_key. The seed public key is derived from this same key."
  type        = string
}

variable "base_image_url" {
  type    = string
  default = "https://cloud-images.ubuntu.com/releases/24.04/release/ubuntu-24.04-server-cloudimg-amd64.img"
}

variable "base_image_checksum" {
  type    = string
  default = "sha256:9fa17e6ba43609bdcf9929b7f73bf2de2a54f65cc4a9e2b4f52ffe1d033c62a0"
}
