variable "project_id"            { type = string }
variable "env"                   { type = string }
variable "notification_channels" { type = list(string); default = [] }
