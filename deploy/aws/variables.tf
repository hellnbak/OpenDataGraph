variable "name" {
  description = "Resource name prefix."
  type        = string
  default     = "opendatagraph"
}

variable "vpc_id" {
  description = "VPC for private OpenDataGraph backing services."
  type        = string
}

variable "subnet_ids" {
  description = "Private subnet identifiers in at least two availability zones."
  type        = list(string)
  validation {
    condition     = length(var.subnet_ids) >= 2
    error_message = "At least two private subnet identifiers are required."
  }
}

variable "application_security_group_ids" {
  description = "Security groups used by OpenDataGraph API and worker workloads."
  type        = list(string)
}

variable "opensearch_principal_arns" {
  description = "IAM principals allowed to access the OpenSearch domain."
  type        = list(string)
  validation {
    condition     = length(var.opensearch_principal_arns) > 0
    error_message = "At least one OpenSearch IAM principal ARN is required."
  }
}

variable "tags" {
  description = "Tags applied to managed resources."
  type        = map(string)
  default     = {}
}
