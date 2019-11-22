aiowamp
=======

.. automodule:: aiowamp

   
   
   .. rubric:: Functions

   .. autosummary::
   
      CancelMode
      InvocationPolicy
      MatchPolicy
      build_message_from_list
      connect
      connect_raw_socket
      connect_transport
      connect_web_socket
      error_to_exception
      exception_to_invocation_error
      get_message_cls
      get_transport_factory
      is_message_type
      join_realm
      message_as_type
      register_error_response
      register_message_cls
      register_transport_factory
      set_invocation_error
   
   

   
   
   .. rubric:: Classes

   .. autosummary::
   
      AuthKeyring
      AuthKeyringABC
      AuthMethodABC
      BlackWhiteList
      CRAuth
      Call
      CallABC
      Client
      ClientABC
      CommonTransportConfig
      IDGenerator
      IDGeneratorABC
      Invocation
      InvocationABC
      InvocationProgress
      InvocationResult
      JSONSerializer
      MessageABC
      MessagePackSerializer
      RawSocketTransport
      SerializerABC
      Session
      SessionABC
      SubscriptionEvent
      SubscriptionEventABC
      TicketAuth
      TransportABC
      URI
      WebSocketTransport
   
   

   
   
   .. rubric:: Exceptions

   .. autosummary::
   
      AbortError
      AuthError
      BaseError
      ClientClosed
      ErrorResponse
      Interrupt
      InvalidMessage
      InvocationError
      TransportError
      UnexpectedMessageError
   
   