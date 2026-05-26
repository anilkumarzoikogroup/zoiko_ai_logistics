variable "project_id"              { type = string }
variable "region"                  { type = string }
variable "env"                     { type = string }
variable "writer_service_accounts" {
  type    = list(string)
  default = []
}
