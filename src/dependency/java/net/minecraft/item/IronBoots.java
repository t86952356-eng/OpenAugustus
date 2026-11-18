package net.minecraft.item;

import client.event.PostMotionObserver;
import client.util.ExtendedListenerController;
import client.util.ListenerAdapter10;
import com.google.gson.JsonElement;
import com.google.gson.JsonPrimitive;

public class IronBoots extends ListenerAdapter10 {
   public PostMotionObserver postMotionObserver;
   public boolean enabled;

   @Override
   public JsonElement getJsonElement() {
      // Android port: rewritten from a cast ternary to if/else - javac 17.0.21 emitted an
      // Object StackMapTable frame for the ternary merge point, which fails HotSpot
      // -Xverify:all ("Bad return type" VerifyError on net/47bX). Identical semantics.
      if (this.postMotionObserver instanceof ExtendedListenerController) {
         return new JsonPrimitive(this.postMotionObserver.getValue());
      }
      return super.getJsonElement();
   }

   @Override
   public double getValue() {
      return this.postMotionObserver.getValue();
   }

   public ListenerAdapter10 getListenerAdapter10() {
      this.enabled = true;
      return this;
   }

   public IronBoots(DefaultItemEntry defaultItemEntry, PostMotionObserver postMotionObserver2) {
      super(defaultItemEntry);
      this.postMotionObserver = postMotionObserver2;
   }

   @Override
   public String toString() {
      return (this.enabled ? "return " : "") + this.postMotionObserver.toString();
   }
}
