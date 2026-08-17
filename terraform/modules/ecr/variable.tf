variable "repository_name" {
  type = string
}

variable "environment" {
  type = string
  validation {
    condition = contains(["dev", "prod", "staging"], var.environment)
	error_message = "The environment variable must be dev, staging, or prod."
  }
}
