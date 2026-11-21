export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  graphql_public: {
    Tables: {
      [_ in never]: never
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      graphql: {
        Args: {
          extensions?: Json
          operationName?: string
          query?: string
          variables?: Json
        }
        Returns: Json
      }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
  public: {
    Tables: {
      aceites_termo: {
        Row: {
          aceito_em: string
          cedente_id: string
          id: string
          ip: string | null
          termo_versao: string
          user_agent: string | null
        }
        Insert: {
          aceito_em?: string
          cedente_id: string
          id?: string
          ip?: string | null
          termo_versao: string
          user_agent?: string | null
        }
        Update: {
          aceito_em?: string
          cedente_id?: string
          id?: string
          ip?: string | null
          termo_versao?: string
          user_agent?: string | null
        }
        Relationships: []
      }
      batimentos: {
        Row: {
          alertas: number | null
          detalhe: Json
          etapa: string
          falhas: number | null
          fim: string | null
          id: number
          inicio: string
          lidos: number | null
          ok: boolean | null
        }
        Insert: {
          alertas?: number | null
          detalhe?: Json
          etapa: string
          falhas?: number | null
          fim?: string | null
          id?: never
          inicio: string
          lidos?: number | null
          ok?: boolean | null
        }
        Update: {
          alertas?: number | null
          detalhe?: Json
          etapa?: string
          falhas?: number | null
          fim?: string | null
          id?: never
          inicio?: string
          lidos?: number | null
          ok?: boolean | null
        }
        Relationships: []
      }
      cedente_contas: {
        Row: {
          atualizado_em: string
          cedente_id: string
          concluida_em: string | null
          id: string
          login: string | null
          milhasflow_enviado_em: string | null
          milhasflow_erro: string | null
          milhasflow_id: string | null
          observacao: string | null
          ordem: number
          programa: string
          status: string
        }
        Insert: {
          atualizado_em?: string
          cedente_id: string
          concluida_em?: string | null
          id?: string
          login?: string | null
          milhasflow_enviado_em?: string | null
          milhasflow_erro?: string | null
          milhasflow_id?: string | null
          observacao?: string | null
          ordem?: number
          programa: string
          status?: string
        }
        Update: {
          atualizado_em?: string
          cedente_id?: string
          concluida_em?: string | null
          id?: string
          login?: string | null
          milhasflow_enviado_em?: string | null
          milhasflow_erro?: string | null
          milhasflow_id?: string | null
          observacao?: string | null
          ordem?: number
          programa?: string
          status?: string
        }
        Relationships: []
      }
      cedente_credenciais: {
        Row: {
          atualizado_em: string
          campo: string
          cedente_id: string
          id: string
          programa: string
          valor_cifrado: string
        }
        Insert: {
          atualizado_em?: string
          campo: string
          cedente_id: string
          id?: string
          programa: string
          valor_cifrado: string
        }
        Update: {
          atualizado_em?: string
          campo?: string
          cedente_id?: string
          id?: string
          programa?: string
          valor_cifrado?: string
        }
        Relationships: []
      }
      cedentes: {
        Row: {
          ativo: boolean
          atualizado_em: string
          aviso_contas_confirmado_em: string | null
          banco: string | null
          chave_pix: string | null
          colaborador_id: string
          convite_id: string | null
          cpf: string
          criado_em: string
          data_nascimento: string | null
          email_criado: string | null
          id: string
          identificador: string
          nome_completo: string
          pix_tipo: string | null
          pontos_esfera: number
          pontos_latam: number
          pontos_livelo: number
          pontos_smiles: number
          revisado_em: string | null
          revisado_por: string | null
          status: string
          telefone: string | null
          token_acesso: string
        }
        Insert: {
          ativo?: boolean
          atualizado_em?: string
          aviso_contas_confirmado_em?: string | null
          banco?: string | null
          chave_pix?: string | null
          colaborador_id: string
          convite_id?: string | null
          cpf: string
          criado_em?: string
          data_nascimento?: string | null
          email_criado?: string | null
          id?: string
          identificador: string
          nome_completo: string
          pix_tipo?: string | null
          pontos_esfera?: number
          pontos_latam?: number
          pontos_livelo?: number
          pontos_smiles?: number
          revisado_em?: string | null
          revisado_por?: string | null
          status?: string
          telefone?: string | null
          token_acesso: string
        }
        Update: {
          ativo?: boolean
          atualizado_em?: string
          aviso_contas_confirmado_em?: string | null
          banco?: string | null
          chave_pix?: string | null
          colaborador_id?: string
          convite_id?: string | null
          cpf?: string
          criado_em?: string
          data_nascimento?: string | null
          email_criado?: string | null
          id?: string
          identificador?: string
          nome_completo?: string
          pix_tipo?: string | null
          pontos_esfera?: number
          pontos_latam?: number
          pontos_livelo?: number
          pontos_smiles?: number
          revisado_em?: string | null
          revisado_por?: string | null
          status?: string
          telefone?: string | null
          token_acesso?: string
        }
        Relationships: []
      }
      config_markup_extensao: {
        Row: {
          atualizado_em: string
          atualizado_por: string | null
          escopo: string
          id: boolean
          tipo: string
          valor: number
        }
        Insert: {
          atualizado_em?: string
          atualizado_por?: string | null
          escopo?: string
          id?: boolean
          tipo?: string
          valor?: number
        }
        Update: {
          atualizado_em?: string
          atualizado_por?: string | null
          escopo?: string
          id?: boolean
          tipo?: string
          valor?: number
        }
        Relationships: []
      }
      config_precos_extensao: {
        Row: {
          atualizado_em: string
          atualizado_por: string | null
          milheiro_manual: number | null
          programa: string
        }
        Insert: {
          atualizado_em?: string
          atualizado_por?: string | null
          milheiro_manual?: number | null
          programa: string
        }
        Update: {
          atualizado_em?: string
          atualizado_por?: string | null
          milheiro_manual?: number | null
          programa?: string
        }
        Relationships: []
      }
      clubes: {
        Row: {
          ativo: boolean
          atualizado_em: string
          avisado_venc: string | null
          conta_id: string
          custo_mensal: number | null
          dia_venc: number | null
          membro_desde: string | null
          meses_ativo: number | null
          pontos_mes: number | null
          programa: string
          titular: string
        }
        Insert: {
          ativo?: boolean
          atualizado_em?: string
          avisado_venc?: string | null
          conta_id: string
          custo_mensal?: number | null
          dia_venc?: number | null
          membro_desde?: string | null
          meses_ativo?: number | null
          pontos_mes?: number | null
          programa: string
          titular: string
        }
        Update: {
          ativo?: boolean
          atualizado_em?: string
          avisado_venc?: string | null
          conta_id?: string
          custo_mensal?: number | null
          dia_venc?: number | null
          membro_desde?: string | null
          meses_ativo?: number | null
          pontos_mes?: number | null
          programa?: string
          titular?: string
        }
        Relationships: []
      }
      clubes_eventos: {
        Row: {
          conta_id: string
          de: string | null
          em: string
          id: number
          para: string | null
          programa: string
          tipo: string
          titular: string
        }
        Insert: {
          conta_id: string
          de?: string | null
          em?: string
          id?: never
          para?: string | null
          programa: string
          tipo: string
          titular: string
        }
        Update: {
          conta_id?: string
          de?: string | null
          em?: string
          id?: never
          para?: string | null
          programa?: string
          tipo?: string
          titular?: string
        }
        Relationships: []
      }
      contas_emissao: {
        Row: {
          atualizado_em: string
          clube_ativo: boolean
          conta_id: string
          cpf_limite: number
          cpf_usados: number
          cpm: number | null
          liberacoes: Json
          programa: string
          saldo: number
          titular: string
        }
        Insert: {
          atualizado_em?: string
          clube_ativo?: boolean
          conta_id: string
          cpf_limite?: number
          cpf_usados?: number
          cpm?: number | null
          liberacoes?: Json
          programa: string
          saldo?: number
          titular: string
        }
        Update: {
          atualizado_em?: string
          clube_ativo?: boolean
          conta_id?: string
          cpf_limite?: number
          cpf_usados?: number
          cpm?: number | null
          liberacoes?: Json
          programa?: string
          saldo?: number
          titular?: string
        }
        Relationships: []
      }
      convites: {
        Row: {
          ativo: boolean
          codigo: string
          colaborador_id: string
          criado_em: string
          id: string
          ultimo_uso_em: string | null
          usos: number
        }
        Insert: {
          ativo?: boolean
          codigo: string
          colaborador_id: string
          criado_em?: string
          id?: string
          ultimo_uso_em?: string | null
          usos?: number
        }
        Update: {
          ativo?: boolean
          codigo?: string
          colaborador_id?: string
          criado_em?: string
          id?: string
          ultimo_uso_em?: string | null
          usos?: number
        }
        Relationships: []
      }
      execucoes: {
        Row: {
          alterados: number | null
          erro: string | null
          executado_em: string
          id: number
          novos: number | null
          sumiram: number | null
          voos_lidos: number | null
        }
        Insert: {
          alterados?: number | null
          erro?: string | null
          executado_em?: string
          id?: never
          novos?: number | null
          sumiram?: number | null
          voos_lidos?: number | null
        }
        Update: {
          alterados?: number | null
          erro?: string | null
          executado_em?: string
          id?: never
          novos?: number | null
          sumiram?: number | null
          voos_lidos?: number | null
        }
        Relationships: []
      }
      fusos_aeroporto: {
        Row: {
          fuso: string
          iata: string
          visto_em: string
        }
        Insert: {
          fuso: string
          iata: string
          visto_em?: string
        }
        Update: {
          fuso?: string
          iata?: string
          visto_em?: string
        }
        Relationships: []
      }
      historico: {
        Row: {
          adiado_ate: string | null
          adiado_por: string | null
          atendente_id: string | null
          aviso_enviado_em: string | null
          aviso_enviado_por: string | null
          aviso_volly_id: string | null
          campo: string | null
          detectado_em: string
          evento: string
          id: number
          ignorado_em: string | null
          ignorado_por: string | null
          notificado: boolean
          origem: string
          resolvido: boolean
          valor_antigo: string | null
          valor_novo: string | null
          verificado_em: string | null
          verificado_por: string | null
          voo_id: string
        }
        Insert: {
          adiado_ate?: string | null
          adiado_por?: string | null
          atendente_id?: string | null
          aviso_enviado_em?: string | null
          aviso_enviado_por?: string | null
          aviso_volly_id?: string | null
          campo?: string | null
          detectado_em?: string
          evento: string
          id?: never
          ignorado_em?: string | null
          ignorado_por?: string | null
          notificado?: boolean
          origem: string
          resolvido?: boolean
          valor_antigo?: string | null
          valor_novo?: string | null
          verificado_em?: string | null
          verificado_por?: string | null
          voo_id: string
        }
        Update: {
          adiado_ate?: string | null
          adiado_por?: string | null
          atendente_id?: string | null
          aviso_enviado_em?: string | null
          aviso_enviado_por?: string | null
          aviso_volly_id?: string | null
          campo?: string | null
          detectado_em?: string
          evento?: string
          id?: never
          ignorado_em?: string | null
          ignorado_por?: string | null
          notificado?: boolean
          origem?: string
          resolvido?: boolean
          valor_antigo?: string | null
          valor_novo?: string | null
          verificado_em?: string | null
          verificado_por?: string | null
          voo_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "historico_atendente_id_fkey"
            columns: ["atendente_id"]
            isOneToOne: false
            referencedRelation: "perfis"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "historico_voo_id_fkey"
            columns: ["voo_id"]
            isOneToOne: false
            referencedRelation: "voos"
            referencedColumns: ["id"]
          },
        ]
      }
      links_pdf: {
        Row: {
          arquivo: string | null
          atualizado_em: string
          companhia: string | null
          localizador: string
          origem: string | null
          pedido: string | null
          sobrenome: string | null
          url: string | null
          util: boolean | null
        }
        Insert: {
          arquivo?: string | null
          atualizado_em?: string
          companhia?: string | null
          localizador: string
          origem?: string | null
          pedido?: string | null
          sobrenome?: string | null
          url?: string | null
          util?: boolean | null
        }
        Update: {
          arquivo?: string | null
          atualizado_em?: string
          companhia?: string | null
          localizador?: string
          origem?: string | null
          pedido?: string | null
          sobrenome?: string | null
          url?: string | null
          util?: boolean | null
        }
        Relationships: []
      }
      malha_checagens: {
        Row: {
          chave: string
          ultima: string
          vezes: number
        }
        Insert: {
          chave: string
          ultima: string
          vezes?: number
        }
        Update: {
          chave?: string
          ultima?: string
          vezes?: number
        }
        Relationships: []
      }
      malha_cota: {
        Row: {
          id: number
          limite: number | null
          reset_em: string | null
          restantes: number | null
          visto_em: string
        }
        Insert: {
          id: number
          limite?: number | null
          reset_em?: string | null
          restantes?: number | null
          visto_em: string
        }
        Update: {
          id?: number
          limite?: number | null
          reset_em?: string | null
          restantes?: number | null
          visto_em?: string
        }
        Relationships: []
      }
      notas: {
        Row: {
          autor_id: string
          criado_em: string
          id: number
          texto: string
          voo_id: string
        }
        Insert: {
          autor_id: string
          criado_em?: string
          id?: never
          texto: string
          voo_id: string
        }
        Update: {
          autor_id?: string
          criado_em?: string
          id?: never
          texto?: string
          voo_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "notas_autor_id_fkey"
            columns: ["autor_id"]
            isOneToOne: false
            referencedRelation: "perfis"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "notas_voo_id_fkey"
            columns: ["voo_id"]
            isOneToOne: false
            referencedRelation: "voos"
            referencedColumns: ["id"]
          },
        ]
      }
      observacoes: {
        Row: {
          origem: string
          partida: string | null
          rota: string | null
          situacao: string | null
          visto_em: string
          voo_id: string
        }
        Insert: {
          origem: string
          partida?: string | null
          rota?: string | null
          situacao?: string | null
          visto_em?: string
          voo_id: string
        }
        Update: {
          origem?: string
          partida?: string | null
          rota?: string | null
          situacao?: string | null
          visto_em?: string
          voo_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "observacoes_voo_id_fkey"
            columns: ["voo_id"]
            isOneToOne: false
            referencedRelation: "voos"
            referencedColumns: ["id"]
          },
        ]
      }
      pendencias: {
        Row: {
          cia: string
          criado_em: string
          id: number
          localizador: string
          motivo: string | null
        }
        Insert: {
          cia: string
          criado_em?: string
          id?: never
          localizador: string
          motivo?: string | null
        }
        Update: {
          cia?: string
          criado_em?: string
          id?: never
          localizador?: string
          motivo?: string | null
        }
        Relationships: []
      }
      perfis: {
        Row: {
          ativo: boolean
          criado_em: string
          id: string
          nome: string
          papel: string
        }
        Insert: {
          ativo?: boolean
          criado_em?: string
          id: string
          nome: string
          papel?: string
        }
        Update: {
          ativo?: boolean
          criado_em?: string
          id?: string
          nome?: string
          papel?: string
        }
        Relationships: []
      }
      propostas_volly: {
        Row: {
          aplicado_em: string | null
          campos: Json
          criado_em: string
          descartado_em: string | null
          descartado_por: string | null
          fonte: string | null
          historico_id: number | null
          id: number
          mensagem: string | null
          pedido_em: string | null
          pedido_por: string | null
          resultado: Json
          status: string
          voo_id: string
        }
        Insert: {
          aplicado_em?: string | null
          campos?: Json
          criado_em?: string
          descartado_em?: string | null
          descartado_por?: string | null
          fonte?: string | null
          historico_id?: number | null
          id?: never
          mensagem?: string | null
          pedido_em?: string | null
          pedido_por?: string | null
          resultado?: Json
          status: string
          voo_id: string
        }
        Update: {
          aplicado_em?: string | null
          campos?: Json
          criado_em?: string
          descartado_em?: string | null
          descartado_por?: string | null
          fonte?: string | null
          historico_id?: number | null
          id?: never
          mensagem?: string | null
          pedido_em?: string | null
          pedido_por?: string | null
          resultado?: Json
          status?: string
          voo_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "propostas_volly_historico_id_fkey"
            columns: ["historico_id"]
            isOneToOne: false
            referencedRelation: "historico"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "propostas_volly_voo_id_fkey"
            columns: ["voo_id"]
            isOneToOne: false
            referencedRelation: "voos"
            referencedColumns: ["id"]
          },
        ]
      }
      solicitacoes_checagem: {
        Row: {
          cia: string | null
          concluido_em: string | null
          id: number
          localizador: string
          resultado: string | null
          solicitado_em: string
          solicitado_por: string | null
          status: string
          voo_id: string
        }
        Insert: {
          cia?: string | null
          concluido_em?: string | null
          id?: never
          localizador: string
          resultado?: string | null
          solicitado_em?: string
          solicitado_por?: string | null
          status?: string
          voo_id: string
        }
        Update: {
          cia?: string | null
          concluido_em?: string | null
          id?: never
          localizador?: string
          resultado?: string | null
          solicitado_em?: string
          solicitado_por?: string | null
          status?: string
          voo_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "solicitacoes_checagem_solicitado_por_fkey"
            columns: ["solicitado_por"]
            isOneToOne: false
            referencedRelation: "perfis"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "solicitacoes_checagem_voo_id_fkey"
            columns: ["voo_id"]
            isOneToOne: false
            referencedRelation: "voos"
            referencedColumns: ["id"]
          },
        ]
      }
      promocoes: {
        Row: {
          aviso_fim_em: string | null
          avisado_em: string | null
          cenarios: Json
          criado_em: string
          dados: Json
          fim: string | null
          fonte: string | null
          id: string
          inicio: string | null
          mensagem_url: string | null
          oportunidade: boolean
          programa: string
          resumo: string
          tipo: string
        }
        Insert: {
          aviso_fim_em?: string | null
          avisado_em?: string | null
          cenarios?: Json
          criado_em?: string
          dados?: Json
          fim?: string | null
          fonte?: string | null
          id: string
          inicio?: string | null
          mensagem_url?: string | null
          oportunidade?: boolean
          programa: string
          resumo: string
          tipo: string
        }
        Update: {
          aviso_fim_em?: string | null
          avisado_em?: string | null
          cenarios?: Json
          criado_em?: string
          dados?: Json
          fim?: string | null
          fonte?: string | null
          id?: string
          inicio?: string | null
          mensagem_url?: string | null
          oportunidade?: boolean
          programa?: string
          resumo?: string
          tipo?: string
        }
        Relationships: []
      }
      supervisor_estado: {
        Row: {
          aberto_em: string | null
          avisado_em: string | null
          chave: string
          detalhe: Json
        }
        Insert: {
          aberto_em?: string | null
          avisado_em?: string | null
          chave: string
          detalhe?: Json
        }
        Update: {
          aberto_em?: string | null
          avisado_em?: string | null
          chave?: string
          detalhe?: Json
        }
        Relationships: []
      }
      termos_indicacao: {
        Row: {
          atualizado_em: string
          ativo: boolean
          corpo: string
          criado_em: string
          id: string
          ordem: number
          slug: string
          titulo: string
          versao: string
        }
        Insert: {
          atualizado_em?: string
          ativo?: boolean
          corpo: string
          criado_em?: string
          id?: string
          ordem?: number
          slug: string
          titulo: string
          versao: string
        }
        Update: {
          atualizado_em?: string
          ativo?: boolean
          corpo?: string
          criado_em?: string
          id?: string
          ordem?: number
          slug?: string
          titulo?: string
          versao?: string
        }
        Relationships: []
      }
      turbo: {
        Row: {
          atualizado_em: string
          cpf_limite: number
          cpf_usados: number
          cpm_latam: number | null
          cpm_livelo: number | null
          clube_ativo: boolean
          conta_id: string
          custo_mensal: number | null
          dia_venc: number | null
          liberacoes: Json
          livelo_clube_ativo: boolean
          livelo_conta_id: string | null
          livelo_custo_mensal: number | null
          livelo_pontos_mes: number | null
          milhas_mes: number | null
          saldo_latam: number
          saldo_livelo: number
          status: string | null
          titular: string
          transferencias: Json
        }
        Insert: {
          atualizado_em?: string
          cpf_limite?: number
          cpf_usados?: number
          cpm_latam?: number | null
          cpm_livelo?: number | null
          clube_ativo?: boolean
          conta_id: string
          custo_mensal?: number | null
          dia_venc?: number | null
          liberacoes?: Json
          livelo_clube_ativo?: boolean
          livelo_conta_id?: string | null
          livelo_custo_mensal?: number | null
          livelo_pontos_mes?: number | null
          milhas_mes?: number | null
          saldo_latam?: number
          saldo_livelo?: number
          status?: string | null
          titular: string
          transferencias?: Json
        }
        Update: {
          atualizado_em?: string
          cpf_limite?: number
          cpf_usados?: number
          cpm_latam?: number | null
          cpm_livelo?: number | null
          clube_ativo?: boolean
          conta_id?: string
          custo_mensal?: number | null
          dia_venc?: number | null
          liberacoes?: Json
          livelo_clube_ativo?: boolean
          livelo_conta_id?: string | null
          livelo_custo_mensal?: number | null
          livelo_pontos_mes?: number | null
          milhas_mes?: number | null
          saldo_latam?: number
          saldo_livelo?: number
          status?: string | null
          titular?: string
          transferencias?: Json
        }
        Relationships: []
      }
      voos: {
        Row: {
          ativo: boolean
          balcao: number
          chegada: string | null
          cia: string | null
          classe: string | null
          cliente: string | null
          criado_em: string
          destino: string | null
          embarque: string | null
          emissao_id: string | null
          id: string
          incompleto: string | null
          localizador: string | null
          numero_voo: string | null
          origem: string | null
          passageiros: string | null
          sentido: string | null
          status: string | null
          tags: string | null
          valor_venda: number | null
          visto_em: string | null
        }
        Insert: {
          ativo?: boolean
          balcao?: number
          chegada?: string | null
          cia?: string | null
          classe?: string | null
          cliente?: string | null
          criado_em?: string
          destino?: string | null
          embarque?: string | null
          emissao_id?: string | null
          id: string
          incompleto?: string | null
          localizador?: string | null
          numero_voo?: string | null
          origem?: string | null
          passageiros?: string | null
          sentido?: string | null
          status?: string | null
          tags?: string | null
          valor_venda?: number | null
          visto_em?: string | null
        }
        Update: {
          ativo?: boolean
          balcao?: number
          chegada?: string | null
          cia?: string | null
          classe?: string | null
          cliente?: string | null
          criado_em?: string
          destino?: string | null
          embarque?: string | null
          emissao_id?: string | null
          id?: string
          incompleto?: string | null
          localizador?: string | null
          numero_voo?: string | null
          origem?: string | null
          passageiros?: string | null
          sentido?: string | null
          status?: string | null
          tags?: string | null
          valor_venda?: number | null
          visto_em?: string | null
        }
        Relationships: []
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      adiar_historico: {
        Args: { p_historico_id: number; p_horas: number }
        Returns: undefined
      }
      atribuir_historico: {
        Args: { p_atendente_id: string; p_historico_id: number }
        Returns: undefined
      }
      eh_admin: { Args: never; Returns: boolean }
      eh_colaborador_ativo: { Args: never; Returns: boolean }
      liberar_alertas_segurados: { Args: never; Returns: undefined }
      marcar_historico_resolvido: {
        Args: { p_historico_id: number; p_resolvido: boolean }
        Returns: undefined
      }
      descartar_proposta_volly: {
        Args: { p_proposta_id: number }
        Returns: undefined
      }
      registrar_aviso_cliente: {
        Args: { p_historico_id: number; p_volly_id: string }
        Returns: undefined
      }
      ignorar_historico: {
        Args: { p_historico_id: number }
        Returns: undefined
      }
      pedir_aplicacao_volly: {
        Args: { p_proposta_id: number }
        Returns: undefined
      }
      marcar_historico_verificado: {
        Args: { p_historico_id: number }
        Returns: undefined
      }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  graphql_public: {
    Enums: {},
  },
  public: {
    Enums: {},
  },
} as const

