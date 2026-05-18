# gitops/apps — App-of-Apps дочерние приложения

Каждый файл в этой директории — `Application` CR ArgoCD, который указывает
на конкретную директорию платформы или workload'ов. Корневой `root` Application
из `gitops/bootstrap/root-app.yaml` подхватывает всё содержимое этой папки.

| Application | Source path | Назначение |
|---|---|---|
| `network-policies` | `gitops/platform/network-policies/` | CiliumNetworkPolicy для namespace `apps` |
| `strimzi` | `gitops/platform/strimzi/` | Strimzi Operator + KafkaCluster (генерируется Ansible-ролью) |

По мере появления новых компонентов (Istio, observability, rate-limit, микросервисы)
сюда будут добавляться новые `Application` манифесты.
