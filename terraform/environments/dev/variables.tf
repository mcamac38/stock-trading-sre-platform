variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "environment" {
  type = string
  validation {
    condition     = contains(["dev", "prod", "staging"], var.environment)
    error_message = "The environment variable must be dev, staging, or prod."
  }
}

variable "aws_profile" {
  type    = string
  default = "SRE_Camacho"
}

variable "repository_name" {
  type = string
}